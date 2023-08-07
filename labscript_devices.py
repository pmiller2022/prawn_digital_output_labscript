from labscript import IntermediateDevice, DigitalOut, bitfield, set_passed_properties, Output, compiler, LabscriptError, TriggerableDevice
import numpy as np

class Pod(Output):
    allowed_children = [DigitalOut]

    def __init__(self, name, parent_device, connection, default_value, **kwargs):

        Output.__init__(self, name, parent_device, connection, None, None, None, default_value, **kwargs)
        


    def generate_code(self, hdf5_file):
        Output.generate_code(self, hdf5_file)


    # Method used to calculate and return the times where the digital outputs
    # change state to the PrawnDO Intermediate Device
    def get_update_times(self):
        # Creating a sorted numpy array to store the update times
        update_times = []
        update_times = np.asarray(update_times)
        # Looping through each output to add their unique update times to the
        # sorted array
        for output in self.child_devices:
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
                        if (time - update_times[-1] >= 49e-9):
                            update_times = np.append(update_times, time) 
                    # If this time is less than the smallest value in the list,
                    # just check that it's smaller by at least 50 ns, then 
                    # insert at the beginning of the array
                    elif update_times[0] > time:
                        if (update_times[0] - time >= 49e-9):
                            update_times = np.insert(update_times, 0, time)   
                    # If the time is located not at the beginning or end,
                    # check both the greater and lesser values, and if the
                    # difference between both value is greater than 50ns,
                    # insert between those two existing time values                         
                    else: 
                        index = np.searchsorted(update_times, time)
                        if(time - update_times[index - 1] >= 49e-9) and (update_times[index] - time >= 49e-9):
                            update_times = np.insert(update_times, index, time)
                    
        return update_times
    # Overriding the get_all_outputs method in order to prevent the parent
    # Pseudoclock from pulsing for each output's change of state
    def get_all_outputs(self):
        return []
    

class PrawnDO(IntermediateDevice):
    allowed_children = [Pod, DigitalOut]

    @set_passed_properties(
        property_names={
            'connection_table_properties': [
                'name',
                'com_port',
            ]
        }
    )


    def __init__(self, name, parent_device, com_port, **kwargs):

        IntermediateDevice.__init__(self, name, parent_device, **kwargs)

        self.pod = Pod('pod', self, 'internal', 0)

        self.BLACS_connection = 'PrawnDO: {}'.format(name)

    def add_device(self, device):
        if isinstance(device, DigitalOut):
            (self.pod).add_device(device)
        else:
            IntermediateDevice.add_device(self, device)



    def generate_code(self, hdf5_file):
        IntermediateDevice.generate_code(self, hdf5_file)

        # Creating a numpy array to take the times from the digital outputs
        # where the program needs to change the output
        times = []
        times = np.asarray(times)
        bits = [0] * 16 # Start with a list of 16 zeros
        # Isolating the Pod child device in order to access the output change 
        # times to store in the array
        for line in self.child_devices:
            if isinstance(line, Pod):
                # Retrieving all of the outputs contained within the pods and
                # collecting/consolidating the times when they change
                outputs = line.get_all_children()
                times = line.get_update_times()
                for output in outputs:
                    # Retrieving the time series of each DigitalOut to be stored
                    # as the output word for shifting to the pins
                    output.make_timeseries(output.get_change_times())
                    bits[int(output.connection, 16)] = np.asarray(output.timeseries, dtype = np.uint16)
        # Merge list of lists into an array with a single 16 bit integer column
        do_table = np.array(bitfield(bits, dtype=np.uint16))

        # Making an array to store the number of reps needed for each output
        # word
        reps = []
        reps = np.asarray(reps, dtype = int)

        # Looping through each entry in the times array to calculate the number
        # of 10ns reps between each output word
        for i in range(1, times.size):
            reps = np.append(reps, (int)(round((times[i] - times[i - 1]) / 10e-9)))
        
        reps = np.append(reps, 0)

        # Looping through the waits given by the compiler's wait table to add 
        # the wait instructions
        for wait in compiler.wait_table: 
            # Finding where the wait fits within the times array
            index = np.searchsorted(times, wait)
            if index > 0:
            # Inserting the wait into the output word table and the reps table
                do_table = np.insert(do_table, index, do_table[index - 1])
            else:
                do_table = np.insert(do_table, index, 0)

            reps = np.insert(reps, index, 0)

        # Raising an error if the user adds too many commands, currently maxed 
        # at 23000
        if reps.size > 23010:
            raise LabscriptError (
                "Too Many Commands"
            )

        group = hdf5_file['devices'].require_group(self.name)
        # Adding the output word table and the reps table to the hdf5 file to
        # be used by the blacs worker to execute the sequence
        group.create_dataset('do_data', data=do_table)
        group.create_dataset('reps_data', data=reps)
        group.create_dataset('times_data', data=times)


class PrawnDOTrig(TriggerableDevice):
    allowed_children = [Pod, DigitalOut]

    def __init__(self, name, parent_device, com_port, **kwargs):

        TriggerableDevice.__init__(self, name, parent_device, com_port, **kwargs)

        self.pod = Pod('pod', self, 'internal', 0)

        self.BLACS_connection = 'PrawnDO: {}'.format(name)

    def add_device(self, device):
        if isinstance(device, DigitalOut):
            (self.pod).add_device(device)
        else:
            TriggerableDevice.add_device(self, device)

    def generate_code(self, hdf5_file):
        TriggerableDevice.generate_code(self, hdf5_file)

        # Creating a numpy array to take the times from the digital outputs
        # where the program needs to change the output
        times = []
        times = np.asarray(times)
        bits = [0] * 16 # Start with a list of 16 zeros
        # Isolating the Pod child device in order to access the output change 
        # times to store in the array
        for line in self.child_devices:
            if isinstance(line, Pod):
                # Retrieving all of the outputs contained within the pods and
                # collecting/consolidating the times when they change
                outputs = line.get_all_children()
                times = line.get_update_times()
                for output in outputs:
                    # Retrieving the time series of each DigitalOut to be stored
                    # as the output word for shifting to the pins
                    output.make_timeseries(output.get_change_times())
                    bits[int(output.connection, 16)] = np.asarray(output.timeseries, dtype = np.uint16)
        # Merge list of lists into an array with a single 16 bit integer column
        do_table = np.array(bitfield(bits, dtype=np.uint16))

        # Making an array to store the number of reps needed for each output
        # word
        reps = []
        reps = np.asarray(reps, dtype = int)

        # Looping through each entry in the times array to calculate the number
        # of 10ns reps between each output word
        for i in range(1, times.size):
            reps = np.append(reps, (int)(round((times[i] - times[i - 1]) / 10e-9)))
        
        reps = np.append(reps, 0)

        # Looping through the waits given by the compiler's wait table to add 
        # the wait instructions
        for wait in compiler.wait_table: 
            # Finding where the wait fits within the times array
            index = np.searchsorted(times, wait)
            if index > 0:
            # Inserting the wait into the output word table and the reps table
                do_table = np.insert(do_table, index, do_table[index - 1])
            else:
                do_table = np.insert(do_table, index, 0)

            reps = np.insert(reps, index, 0)

        # Raising an error if the user adds too many commands, currently maxed 
        # at 23000
        if reps.size > 23010:
            raise LabscriptError (
                "Too Many Commands"
            )

        group = hdf5_file['devices'].require_group(self.name)
        # Adding the output word table and the reps table to the hdf5 file to
        # be used by the blacs worker to execute the sequence
        group.create_dataset('do_data', data=do_table)
        group.create_dataset('reps_data', data=reps)
        group.create_dataset('times_data', data=times)
    

    
