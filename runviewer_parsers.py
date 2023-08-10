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
        
        print(self)

        with h5py.File(self.path, "r") as f:
            group = f['devices/' + self.name]

            do_table = group['do_data'][:]
            times_table = group['times_data'][:]
            

        print(do_table)
        digital_outs = {}

        for digiout_name, digiout in self.device.child_list.items():
            print(digiout_name)
            if not digiout_name == "pod":
                do_states = []

                for word in do_table:
                    if (((word >> ((int(digiout.parent_port, 16)) % 16)) & 1) == 1):
                        do_states.append(1.0)
                    else:
                        do_states.append(0.0)
                                   
                output_trace = (np.array(times_table), np.array(do_states))

                name = "do%d" % int(digiout.parent_port, 16)

                digital_outs[name] = output_trace

                add_trace(
                    name,
                    output_trace,
                    self.name,
                    digiout.parent_port
                )
            
        return digital_outs