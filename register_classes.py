from labscript_devices import register_classes

register_classes(
    'PrawnDO',
    BLACS_tab='naqslab_devices.prawn_digital_output_labscript.blacs_tabs.PrawnDOTab',
    runviewer_parser='naqslab_devices.prawn_digital_output_labscript.runviewer_parsers.PrawnDOParser',
)

register_classes(
    '_PrawnDOIntermediateDevice',
    BLACS_tab='',
    runviewer_parser='naqslab_devices.prawn_digital_output_labscript.runviewer_parsers._PrawnDOIntermediateParser'
)