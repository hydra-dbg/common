
Test our global standard configuration
-------------------------------------

::

    >>> import sys, os; sys.path.append(os.getcwd())

    >>> import cfg.globalconfig as globalconfig
    >>> globalconfig.load_global_config("regress/cfg/config/global.cfg",
    ...                                 "regress/cfg/config/user.cfg" )
    >>> config = globalconfig.get_global_config()

    >>> config.has_section("gdb")
    True

    >>> config.getboolean("gdb", "use-gdb-system")
    False

    >>> config.get("gdb", "gdb-executable-path")
    '/virtualpath/gdb-7.8/gdb/gdb'

    >>> config.get("gdb", "python")
    '2.x'

