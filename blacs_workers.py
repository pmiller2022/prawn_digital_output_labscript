from blacs.tab_base_classes import Worker
import labscript_utils.h5_lock, h5py
import labscript_utils
from labscript import LabscriptError
import numpy as np
import re
import time

class PrawnDOInterface(object):
    def __init__(self, com_port):
        global serial; import serial

        self.timeout = 0.5
        self.conn = serial.Serial(com_port, 10000000, timeout=self.timeout)

        ver = self.send_command('ver')
        print(f'Connected: {ver:s}')
        
    def send_command(self, command, readlines=False):
        '''Sends the supplied string command and checks for a response.
        
        Automatically applies the correct termination characters.
        
        Args:
            command (str): Command to send. Termination and encoding is done automatically.
            readlines (bool, optional): Use pyserial's readlines functionality to read multiple
                response lines. Slower as it relies on timeout to terminate reading.

        Returns:
            str: String response from the PrawnDO
        '''
        command += '\r\n'
        self.conn.write(command.encode())

        if readlines:
            resp = self.conn.readlines()
            str_resp = ''.join([st.decode() for st in resp])
        else:
            str_resp = self.conn.readline().decode()

        return str_resp
    
    def send_command_ok(self, command):
        '''Sends the supplied string command and confirms 'ok' response.
        '''

        resp = self.send_command(command)
        if resp != 'ok\r\n':
            raise LabscriptError(f"Command '{command:s}' failed. Got response '{resp}'")
    
    def status(self):
        '''Reads the status of the PrawnDO
        
        Returns:
            (int, int): tuple containing

                - **run-status** (int): Run status code
                - **clock-status** (int): Clock status code
        '''
        resp = self.send_command('sts')
        match = re.match(r"run-status:(\d) clock-status:(\d)(\r\n)?", resp)
        if match:
            return int(match.group(1)), int(match.group(2))
        else:
            raise LabscriptError('PrawnDO invalid status, returned {resp}')

    def add_batch(self, bit_sets, reps):
        '''Sends 'add' commands for each bit_set in bit_sets list. Returns response.'''
        self.conn.write('add\n'.encode())
        for i in range(0, len(reps)):
            self.conn.write('{:04x} '.format(bit_sets[i]).encode()) 
            self.conn.write('{:08x}\n'.format(reps[i]).encode())
        self.conn.write('end\n'.encode())
        resp = self.conn.readline().decode()
        assert resp == 'ok\r\n', f'Program not written successfully, got response {resp}'

    def close(self):
        self.conn.close()

class PrawnDOWorker(Worker):
    def init(self):
        self.intf = PrawnDOInterface(self.com_port)        

        self.smart_cache = {'do_table':None, 'reps':None}

    def _dict_to_int(self, d):
        """Converts dictionary of outputs to an integer mask.
        
        Args:
            d (dict): Dictionary of output states

        Returns:
            int: Integer mask of the 16 output states.
        """
        val = 0
        for conn, value in d.items():
            val |= value << int(conn, 16)

        return val
    
    def _int_to_dict(self, val):
        """Converts an integer mask to a dictionary of outputs.
        
        Args:
            val (int): 16-bit integer mask to convert
            
        Returns:
            dict: Dictonary with output channels as keys and values are boolean states
        """
        return {hex(i):((val >> i) & 1) for i in range(16)}
    
    def check_status(self):
        '''Checks operational status of the PrawnDO.

        Automatically called by BLACS to update status.

        Returns:
            (int, int): Tuple containing:

            - **run-status** (int): Possible values are:

              * 0 : manual mode
              * 1 : transitioning to buffered execution
              * 2 : buffered execution
              * 3 : abort requested
              * 4 : aborting buffered execution
              * 5 : last buffered execution aborted
              * 6 : transitioning to manual mode

            - **clock-status** (int): Possible values are:

              * 0 : internal clock
              * 1 : external clock
        '''

        return self.intf.status()

    def program_manual(self, front_panel_values):
        """Change output states in manual mode.
        
        Returns:
            dict: Output states after command execution.
        """
        value = self._dict_to_int(front_panel_values)
        # send static state
        self.intf.send_command_ok(f'man {value:04x}')
        # confirm state set correctly
        resp = self.intf.send_command('gto')

        return self._int_to_dict(int(resp, 16))
    
    def check_remote_values(self):
        """Checks the remote state of the PrawnDO.
        
        Called automatically by BLACS.
        
        Returns:
            dict: Dictionary of the digital output states.
        """
        resp = self.intf.send_command('gto')

        return self._int_to_dict(int(resp, 16))

    def transition_to_buffered(self, device_name, h5file, initial_values, fresh):

        if fresh:
            self.smart_cache = {'do_table':None, 'reps':None}

        with h5py.File(h5file, 'r') as hdf5_file:
            group = hdf5_file['devices'][device_name]
            self.device_properties = labscript_utils.properties.get(
                hdf5_file, device_name, "device_properties")
            do_table = group['do_data'][()]
            reps = group['reps_data'][()]

        # configure clock from device properties
        ext = self.device_properties['external_clock']
        freq = self.device_properties['clock_frequency']
        self.intf.send_command_ok(f"clk {ext:d} {freq:.0f}")
            
        # only program if things differ from smart cache
        if not (np.array_equal(do_table, self.smart_cache['do_table']) and
                np.array_equal(reps, self.smart_cache['reps'])):
            self.intf.send_command_ok('cls') # clear old program
            self.intf.add_batch(do_table, reps)
            self.smart_cache['do_table'] = do_table
            self.smart_cache['reps'] = reps

        final_values = self._int_to_dict(do_table[-1])

        # start program, waiting for beginning trigger from parent
        self.intf.send_command_ok('run')

        return final_values

    def transition_to_manual(self):
        """Transition to manual mode after buffered execution completion.
        
        Returns:
            bool: `True` if transition to manual is successful.
        """
        while True:
            run_status, _ = self.intf.status()
            if run_status == 0:
                break
            elif run_status in [3,4,5]:
                raise LabscriptError(f'PrawnDO returned status {run_status} in transition to manual')
            
        return True

    def abort_buffered(self):
        """Aborts a currently running buffered execution.
        
        Returns:
            bool: `True` is abort was successful.
        """
        self.intf.send_command_ok('abt')
        # loop until abort complete
        while self.intf.status()[0] != 5:
            time.sleep(0.5)
        return True

    def abort_transition_to_buffered(self):
        """Aborts transition to buffered.
        
        Calls :meth:`abort_buffered`
        """
        return self.abort_buffered()

    def shutdown(self):
        """Closes serial connection to PrawnDO"""
        self.intf.close()
