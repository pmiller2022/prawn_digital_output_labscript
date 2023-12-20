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


        if clock is not None:
            times, clock_value = clock[0], clock[1]
            clock_indices = np.where((clock_value[1:] - clock_value[:-1]) == 1)[0] + 1
            # If initial clock value is 1, then this counts as a rising edge
            # (clock should be 0 before experiment) but this is not picked up
            # by the above code. So we insert it!
            if clock_value[0] == 1:
                clock_indices = np.insert(clock_indices, 0, 0)
            clock_ticks = times[clock_indices]

        # Getting output words, and update times from the shot file
        with h5py.File(self.path, "r") as f:
            device_props = properties.get(f, self.name, 'device_properties')
            self.clock_resolution = device_props['clock_resolution']
            self.trigger_delay = device_props['trigger_delay']
            self.wait_delay = device_props['wait_delay']

            waits = f['waits'][()]
            group = f['devices/' + self.name]

            do_table = group['do_data'][()]
            reps_table = group['reps_data'][()]

        # remove final element from both do and reps (2nd part of stop instruction)
        do_table = np.delete(do_table, -1)
        reps_table = np.delete(reps_table, -1)
        time_deltas_table = reps_table*self.clock_resolution
        # re-add trigger delay
        trigger_index = 0
        t = 0 if clock is None else clock_ticks[trigger_index] + self.trigger_delay
        time_deltas_table[0] += t
        # re-add wait delays (ignoring final one, which is from the 1st part of stop command)
        wait_idxs = np.nonzero(reps_table==0)[0][:-1]
        for wait_idx in wait_idxs:
            if clock is not None:
                t = self.trigger_delay
            else:
                t = self.wait_delay
            time_deltas_table[wait_idx] += t
        # insert t=0 for cumsum, remove final value (from stop instruction)
        times_table = np.cumsum(np.insert(time_deltas_table,0,0.0))[:-1]

        
        # convert do_table back to individual bits for each output
        do_bitfield = np.fliplr( # reverse bit order for indexing by label
            np.unpackbits(
                do_table.reshape(do_table.shape + (1,) # reshape so unpackbits does each number separate
                                 ).byteswap().view(np.uint8), # switch endianness, view at uint8 for unpackbits
                                 axis=1) # unpack along time axis
        )

        digital_outs = {}

        # work down the tree of parent devices to the digital outputs
        for pseudoclock_name, pseudoclock in self.device.child_list.items():
            for clock_line_name, clock_line in pseudoclock.child_list.items():
                for internal_device_name, internal_device in clock_line.child_list.items():
                    for channel_name, channel in internal_device.child_list.items():
                        chan = channel.parent_port.split(' ')[-1]
                        output_trace = (times_table, do_bitfield[:,int(chan,16)])
                        digital_outs[channel_name] = output_trace
                        add_trace(channel_name, output_trace,
                                  self.name, channel.parent_port)
            
        return digital_outs


class _PrawnDOIntermediateParser(object):

    def __init__(self, path, device):
        self.path = path
        self.name = device.name
        self.device = device

    def get_traces(self, add_trace, clock = None):

        return {list(self.device.child_list.keys())[0]: clock}
