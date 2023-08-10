from labscript_devices import register_classes

register_classes(
    'PrawnDO',
    BLACS_tab='naqslab_devices.prawn_do.blacs_tabs.PrawnDOTab',
    runviewer_parser='naqslab_devices.prawn_do.runviewer_parsers.PrawnDOParser',
)


register_classes(
    'PrawnDOTrig',
    BLACS_tab='naqslab_devices.prawn_do.blacs_tabs.PrawnDOTab',
    runviewer_parser=None,
)
