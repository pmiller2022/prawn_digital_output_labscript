from labscript import (
    IntermediateDevice,
    PseudoclockDevice,
    Pseudoclock,
    ClockLine,
    DigitalOut,
    Trigger,
    bitfield,
    set_passed_properties,
    compiler,
    LabscriptError
)
import numpy as np

class _PrawnDOPseudoclock(Pseudoclock):
    """Dummy pseudoclock for use with PrawnDO.
    
    This pseudoclock ensures only one clockline is attached.
    """

    def add_device(self, device):

        if not isinstance(device, _PrawnDOClockline) or self.child_devices:
            # only allow one child dummy clockline
            raise LabscriptError("You are trying to access the special, dummy, Pseudoclock of the PrawnDO "
                                    f"{self.parent_device.name}. This is for internal use only.")
        else:
            Pseudoclock.add_device(self, device)


class _PrawnDOClockline(ClockLine):
    """Dummy clockline for use with PrawnDO
    
    Ensures only a single _PrawnDODirectOutputs is connected to the PrawnDO
    """

    def add_device(self, device):

        if not isinstance(device, _PrawnDigitalOutputs) or self.child_devices:
            # only allow one child device
            raise LabscriptError("You are trying to access the special, dummy, Clockline of the PrawnDO "
                                    f"{self.pseudoclock_device.name}. This is for internal use only.")
        else:
            ClockLine.add_device(self, device)


class _PrawnDigitalOutputs(IntermediateDevice):
    allowed_children = [DigitalOut]

    allowed_channels = ('0', '1', '2', '3',
                        '4', '5', '6', '7',
                        '8', '9', 'A', 'B',
                        'C', 'D', 'E', 'F')

    def __init__(self, name, parent_device,
                 **kwargs):
        """Collective output class for the PrawnDO.
        
        This class aggregates the 16 individual digital outputs of the PrawnDO.
        It is for internal use of the PrawnDO only.

        Args:
            name (str): name to assign
            parent_device (Device): Parent device PrawnDO is connected to
        """

        IntermediateDevice.__init__(self, name, parent_device, **kwargs)
        self.connected_channels = []

    def add_device(self, device):
        """Confirms channel specified is valid before adding
        
        Args:
            device (): Device to attach. Must be a digital output.
                Allowed connections are a string that ends with a 0-F hex
                channel number.
        """

        conn = device.connection
        chan = conn.split(' ')[-1]

        if chan not in self.allowed_channels:
            raise LabscriptError(f'Invalid channel specification: {conn}')
        if chan in self.connected_channels:
            raise LabscriptError(f'Channel {conn} already connected to {self.parent_device.name}')
        
        self.connected_channels.append(chan)
        super().add_device(device)
    

class PrawnDODevice(PseudoclockDevice):
    description = "PrawnDO Pseudoclock device"

    # default specs assuming 100MHz system clock
    clock_limit = 1 / 100e-9
    "Maximum allowable clock rate"
    clock_resolution = 10e-9
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

    allowed_children = [_PrawnDOPseudoclock]

    max_instructions = 30000
    """Maximum number of instructions. Set by zmq timeout when sending the commands."""

    @set_passed_properties(
        property_names={
            'connection_table_properties': [
                'com_port',
            ],
            'device_properties': [
                'clock_frequency',
                'external_clock',
                'clock_limit',
                'clock_resolution',
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
            self.clock_limit *= factor
            self.clock_resolution *= factor
            self.minimum_duration *= factor
            self.wait_delay *= factor
            self.input_response_time *= factor
            self.trigger_delay *= factor
            self.trigger_minimum_duration *= factor

        PseudoclockDevice.__init__(self, name, trigger_device, trigger_connection)

        # set up internal connections to allow digital outputs
        self.__pseudoclock = _PrawnDOPseudoclock(f'{name:s}__pseudoclock', self, '_')
        self.__clockline = _PrawnDOClockline(f'{name:s}__clockline',
                                             self.__pseudoclock, '_')
        self.outputs = _PrawnDigitalOutputs(f'{name:s}__pod', self.__clockline)

        self.BLACS_connection = com_port

    def add_device(self, device):

        if isinstance(device, _PrawnDOPseudoclock):
            super().add_device(device)
        elif isinstance(device, DigitalOut):
            raise LabscriptError(f"Digital outputs must be connected to {self.name:s}.outputs")
        else:
            raise LabscriptError(f"You have connected unsupported {device.name:s} (class {device.__class__}) "
                                 f"to {self.name:s}")


    def generate_code(self, hdf5_file):
        PseudoclockDevice.generate_code(self, hdf5_file)

        bits = [0] * 16 # Start with a list of 16 zeros
        # Isolating the Pod child device in order to access the output change 
        # times to store in the array

        # Retrieving all of the outputs contained within the pods and
        # collecting/consolidating the times when they change
        outputs = self.get_all_outputs()
        times = self.__pseudoclock.times[self.__clockline]

        if len(times) == 0:
            # no instructions, so return
            return
        
        for output in outputs:
            # Retrieving the time series of each DigitalOut to be stored
            # as the output word for shifting to the pins
            output.make_timeseries(times)
            chan = output.connection.split(' ')[-1]
            bits[int(chan, 16)] = np.asarray(output.timeseries, dtype = np.uint16)
        # Merge list of lists into an array with a single 16 bit integer column
        do_table = np.array(bitfield(bits, dtype=np.uint16))

        # Now create the reps array (ie times between changes in number of clock cycles)
        reps = np.rint(np.diff(times)/self.clock_resolution).astype(np.uint32)
        
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

    allowed_children = [Trigger]

    @set_passed_properties(
        property_names={
            'connection_table_properties': [
                'com_port',
            ],
            'device_properties': [
                'clock_frequency',
                'external_clock',
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

        IntermediateDevice.__init__(self, f'{name:s}_dummy_parent', parent_device, **kwargs)

        self._prawn_device = PrawnDODevice(f'{name:s}',
                                           self, 'internal',
                                           com_port,
                                           clock_frequency,
                                           external_clock)
        
    def add_device(self, device):

        if isinstance(device, Trigger):
            # the internal Trigger line for the PrawnDODevice
            super().add_device(device)
        elif isinstance(device, DigitalOut):
            # pass Digital Outputs to PrawnDODevice
            # this really shouldn't be used
            self._prawn_device.add_device(device)
        else:
            raise LabscriptError(f"You have connected unsupported {device.name:s} (class {device.__class__}) "
                                 f"to {self.name:s}")