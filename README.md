# Prawn Digital Output Labscript Driver

This program allows the [Prawn Digital Output](https://github.com/pmiller2022/prawn_digital_output/tree/main) Raspberry Pi Pico code to work with Labscript. This code was developed off the [labscript driver for digital outputs](https://github.com/carterturn/zwierlein_labscript_user_devices/tree/basis/prawn_do) developed by Carter Turnbaugh.

The default PrawnDO takes a PseudoclockDevice as a parent and uses that as a trigger and to control. The LabscriptDevices code also contains a PrawnDOTrig which takes a DigitalOut or a trigger as a parent device.

Runviewer Parser not currently supported for PrawnDOTrig device

## Example Connection Table
<img width="628" alt="conn_table" src="https://github.com/pmiller2022/prawn_digital_output_labscript/assets/75953337/e2b42a52-4413-4708-b5bd-46628bacdf07">

## Example Connection Table With TriggerableDevice
<img width="618" alt="conn_table_trigPNG" src="https://github.com/pmiller2022/prawn_digital_output_labscript/assets/75953337/a7d39627-6316-4845-b4f8-16cfeb4132a8">
