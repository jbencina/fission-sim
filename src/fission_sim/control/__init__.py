"""Control-layer components.

The control layer sits above physics in the four-layer dependency stack
(Visualization → Control → Physics → Engine). Control modules read
physics outputs and operator inputs and produce actuator demands that
physics modules consume.

First inhabitant: ``PressurizerController`` (M2). The ``RodController``
is conceptually a control component but lives in ``physics/`` for
historical reasons; that is not refactored in M2.
"""
