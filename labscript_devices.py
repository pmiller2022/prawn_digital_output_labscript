from labscript import (
    IntermediateDevice,
    PseudoclockDevice,
    Pseudoclock,
    Clockline,
    DigitalOut,
    bitfield,
    set_passed_properties,
    Output,
    compiler,
    LabscriptError
)
import numpy as np

class _PrawnDODummyPseudoclock(Pseudoclock):
    """Dummy pseudoclock for use with PrawnDO.
    
    This pseudoclock ensures only one clockline is attached.
    """

    def add_device(self, device):

        if not isinstance(device, _PrawnDODummyClockline) or self.child_devices:
            # only allow one child dummy clockline
            raise LabscriptError("You are trying to access the special, dummy, Pseudoclock of the PrawnDO "
                                    f"{self.parent_device.name}. This is for internal use only.")
        else:
            Pseudoclock.add_device(self, device)

    
    def generate_code(self, *args, **kwargs):
        # do nothing, dummy class
        pass


class _PrawnDODummyClockline(Clockline):
    """Dummy clockline for use with PrawnDO
    
    Ensures only a single Pod is connected to the PrawnDO
    """

    def add_device(self, device):

        if not isinstance(device, _Pod) or self.child_devices:
            # only allow one child Pod device
            raise LabscriptError("You are trying to access the special, dummy, Clockline of the PrawnDO "
                                    f"{self.pseudoclock_device.name}. This is for internal use only.")
        else:
            Clockline.add_device(self, device)


    def generate_code(self, *args, **kwargs):
        # do nothing, dummy class
        pass


class _Pod(IntermediateDevice):
    allowed_children = [DigitalOut]

    def __init__(self, name, parent_device, min_duration,
                 **kwargs):
        """Collective output class for the PrawnDO.
        
        This class aggregates the 16 individual digital outputs of the PrawnDO.
        It is for internal use of the PrawnDO only.

        Args:
            name (str): name to assign
            parent_device (Device): Parent device PrawnDO is connected to
            min_duration (float): Minimum time between updates on the outputs, in seconds.
        """

        self.min_duration = min_duration
        IntermediateDevice.__init__(self, name, parent_device, **kwargs)


    def get_update_times(self):
        """Overridden method that collects and condenses update times across all 16 outputs."""
        # TODO: this is very fragile to timing edge cases
        # Creating a sorted numpy array to store the update times
        update_times = []
        update_times = np.asarray(update_times)
        # Looping through each output to add their unique update times to the
        # sorted array
        for output in self.child_devices:
            # do checks on instructions, ensures all outputs have a default state
            output.do_checks((0,))
            # Checking each update time of each output to see if it is unique
            # enough (>= 50ns difference compared to other times)
            for time in output.get_change_times():
                # First check if the time is already in the update times array
                if time not in update_times:
                    # If the array is empty, add this time to it
                    if update_times.size == 0:
                        update_times = np.append(update_times, time)
                    # If this time is greater than the greatest value currently
                    # in the list, just check to make sure its greater by 50ns
                    # and if it is, append to the array
                    elif update_times[-1] < time:
                        if (time - update_times[-1] >= self.min_duration):
                            update_times = np.append(update_times, time) 
                    # If this time is less than the smallest value in the list,
                    # just check that it's smaller by at least 50 ns, then 
                    # insert at the beginning of the array
                    elif update_times[0] > time:
                        if (update_times[0] - time >= self.min_duration):
                            update_times = np.insert(update_times, 0, time)   
                    # If the time is located not at the beginning or end,
                    # check both the greater and lesser values, and if the
                    # difference between both value is greater than 50ns,
                    # insert between those two existing time values                         
                    else: 
                        index = np.searchsorted(update_times, time)
                        if ((time - update_times[index - 1] >= self.min_duration) 
                            and (update_times[index] - time >= self.min_duration)):
                            
                            update_times = np.insert(update_times, index, time)
                    
        return update_times

    def get_all_outputs(self):
        """Overridden in order to prevent parent Pseudoclock from ticking
        for each output's change of state"""
        return []
    

class PrawnDODevice(PseudoclockDevice):
    description = "PrawnDO Pseudoclock device"

    # default specs assuming 100MHz system clock
    resolution = 10e-9
    "Minimum resolvable unit of time, corresponsd to system clock period."
    minimum_duration = 50e-9
    "Minimum time between updates on the outputs."
    wait_delay = 40e-9
    "Minimum required length of wait before a retrigger can be detected."
    input_response_time = 50e-9
    "Time between hardware trigger and output starting."
    trigger_delay = input_response_time
    trigger_minimum_duration = 160e-9
    "Minimum required duration of hardware trigger. A fairly large over-estimate."

    allowed_children = [_PrawnDODummyPseudoclock]

    max_instructions = 23010
    """Maximum number of instructions. Set by zmq timeout when sending the commands."""

    @set_passed_properties(
        property_names={
            'connection_table_properties': [
                'com_port',
            ],
            'device_properties': [
                'clock_frequency',
                'external_clock',
                'resolution',
                'minimum_duration',
                'input_response_time',
                'trigger_delay',
                'trigger_minimum_duration',
                'wait_delay',
            ]
        }
    )


    def __init__(self, name, 
                 trigger_device = None,
                 trigger_connection = None,
                 com_port = 'COM1',
                 clock_frequency = 100e6,
                 external_clock = False,
                ):
        """PrawnDO digital output device.
        
        This labscript device provides general purpose digital outputs
        using a Raspberry Pi Pico with custom firmware.

        Args:
            name (str): python variable name to assign to the PrawnDO
            trigger_device (:class:`~labscript.IntermediateDevice`, optional):
                Device that will send the starting hardware trigger.
            trigger_connection (str, optional): Which output of the `trigger_device`
                is connected to the PrawnDO hardware trigger input.
            com_port (str): COM port assinged to the PrawnDO by the OS.
                Takes the form of `COMd` where `d` is an integer.
            clock_frequency (float, optional): System clock frequency, in Hz.
                Must be less than 133 MHz. Default is `100e6`.
            external_clock (bool, optional): Whether to use an external clock.
                Default is `False`.
        """

        if clock_frequency > 133e6:
            raise ValueError('Clock frequency must be less than 133 MHz')
        
        self.external_clock = external_clock
        self.clock_frequency = clock_frequency
        # update specs based on clock frequency
        if self.clock_frequency != 100e6:
            # factor to scale times by
            factor = 100e6/self.clock_frequency
            self.resolution *= factor
            self.minimum_duration *= factor
            self.wait_delay *= factor
            self.input_response_time *= factor
            self.trigger_delay *= factor
            self.trigger_minimum_duration *= factor

        PseudoclockDevice.__init__(self, name, trigger_device, trigger_connection)

        # set up internal connections to allow digital outputs
        self.__dummy_pseudoclock = _PrawnDODummyPseudoclock(f'{name:s}__dummy_pseudoclock', self, '_')
        self.__dummy_clockline = _PrawnDODummyClockline(f'{name:s}__dummy_clockline',
                                                        self.__dummy_pseudoclock, '_')
        self.__pod = _Pod(f'{name:s}__pod', self.__dummy_clockline, self.minimum_duration)

        self.BLACS_connection = com_port

    def add_device(self, device):

        if isinstance(device, DigitalOut):
            self.__pod.add_device(device)
        else:
            raise LabscriptError(f"You have connected unsupported {device.name:s} (class {device.__class__:s}) "
                                 "to {self.name:s}")


    def generate_code(self, hdf5_file):
        PseudoclockDevice.generate_code(self, hdf5_file)

        bits = [0] * 16 # Start with a list of 16 zeros
        # Isolating the Pod child device in order to access the output change 
        # times to store in the array

        # Retrieving all of the outputs contained within the pods and
        # collecting/consolidating the times when they change
        outputs = self.__pod.get_all_children()
        times = self.__pod.get_update_times()
        if len(times) == 0:
            # no instructions, so return
            return
        
        for output in outputs:
            # Retrieving the time series of each DigitalOut to be stored
            # as the output word for shifting to the pins
            output.make_timeseries(times)
            bits[int(output.connection, 16)] = np.asarray(output.timeseries, dtype = np.uint16)
        # Merge list of lists into an array with a single 16 bit integer column
        do_table = np.array(bitfield(bits, dtype=np.uint16))

        # Now create the reps array (ie times between changes in number of clock cycles)
        reps = np.rint(np.diff(times)/self.resolution).astype(np.uint32)
        
        # add stop command sequence
        reps = np.append(reps, 0) # causes last instruction to hold
        # next two indicate the stop
        do_table = np.append(do_table, 0) # this value is ignored
        reps = np.append(reps, 0)

        # Looping through the waits given by the compiler's wait table to add 
        # the wait instructions
        for wait in compiler.wait_table: 
            # Finding where the wait fits within the times array
            index = np.searchsorted(times, wait)
            # Inserting the wait into the output word table and the reps table
            do_table = np.insert(do_table, index, do_table[index - 1])
            reps = np.insert(reps, index, 0)

        # Raising an error if the user adds too many commands, currently maxed 
        # at 23000
        if reps.size > self.max_instructions:
            raise LabscriptError (
                "Too Many Commands"
            )

        group = hdf5_file['devices'].require_group(self.name)
        # Adding the output word table and the reps table to the hdf5 file to
        # be used by the blacs worker to execute the sequence
        group.create_dataset('do_data', data=do_table)
        group.create_dataset('reps_data', data=reps)


class PrawnDO(IntermediateDevice):
    description = "PrawnDO"

    allowed_children = [PrawnDODevice]

    @set_passed_properties(
        property_names={
            'connection_table_properties': [
                'com_port',
            ],
            'device_properties': [
                'clock_frequency',
                'external_clock',
                'resolution',
                'minimum_duration',
                'input_response_time',
                'trigger_delay',
                'trigger_minimum_duration',
                'wait_delay',
            ]
        }
    )


    def __init__(self, name, parent_device, com_port,
                 clock_frequency = 100e6,
                 external_clock = False,
                 **kwargs):
        """PrawnDO digital output device.
        
        This labscript device provides general purpose digital outputs
        using a Raspberry Pi Pico with custom firmware.

        Args:
            name (str): python variable name to assign to the PrawnDO
            parent_device (:class:`~labscript.Device`): Device that will send the
                starting hardware trigger.
            com_port (str): COM port assinged to the PrawnDO by the OS.
                Takes the form of `COMd` where `d` is an integer.
            clock_frequency (float, optional): System clock frequency, in Hz.
                Must be less than 133 MHz. Default is `100e6`.
            external_clock (bool, optional): Whether to use an external clock.
                Default is `False`.
        """
        
        self.external_clock = external_clock
        self.clock_frequency = clock_frequency

        IntermediateDevice.__init__(self, name, parent_device, **kwargs)

        self.BLACS_connection = com_port

        self.add_device(PrawnDODevice(f'{name:s}_prawndodevice',
                                      self, 'internal',
                                      com_port,
                                      clock_frequency,
                                      external_clock))