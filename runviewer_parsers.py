import labscript_utils.h5_lock  
import h5py
import numpy as np

import labscript_utils.properties as properties

class PrawnDOParser(object):
    def __init__(self, path, device):
        self.path = path
        self.name = device.name
        self.device = device


    def get_traces(self, add_trace, clock = None):


        # Getting the waits, output words, and update times from the shot file
        with h5py.File(self.path, "r") as f:
            waits = (f['waits'][:])
            group = f['devices/' + self.name]

            do_table = group['do_data'][:]
            times_table = group['times_data'][:]
            times_table = np.array(times_table)
            do_table = np.array(do_table)

            # Removing the waits from the output word table to prevent wrong
            # output trace
            for wait, time, timeout in waits:
                index = np.searchsorted(times_table, time)
                do_table = np.delete(do_table, index)
                
            

        digital_outs = {}

        for digiout_name, digiout in self.device.child_list.items():
            # Ignoring the internal pod child object
            if not digiout_name == "pod":
                # This is for if the triggerable prawndo is attached, preventing
                # the runviewer parser from trying to read the parent trigger device
                # if it's a digitalout of the prawndo
                for trig in digiout.child_list:
                    digiout.child_list = {}
                
                do_states = []

                # Reading in the output word from the table and making an array
                # for each output to show when they should go high or low
                for word in do_table:
                    if (((word >> ((int(digiout.parent_port, 16)) % 16)) & 1) == 1):
                        do_states.append(1.0)
                    else:
                        do_states.append(0.0)
                                   
                # Storing the output trace as the update times and the states
                # of the digitalouts at those given times
                output_trace = (times_table, np.array(do_states))

                name = "do%d" % int(digiout.parent_port, 16)

                digital_outs[name] = output_trace

                # Adding the trace to the runviewer parser
                add_trace(
                    name,
                    output_trace,
                    self.name,
                    digiout.parent_port
                )
            
        return digital_outs
