"""The connectors platform: a marketplace of pluggable integrations.

Each connector declares a :class:`~pragya_assistant.connectors.spec.ConnectorSpec`
(identity + auth + config schema + capabilities) and implements the runtime
capability protocols in :mod:`pragya_assistant.connectors.base`. The
:class:`~pragya_assistant.connectors.manager.ConnectorManager` ties the catalog
(available specs) to instances (what the user has enabled) and re-wires the
agent on change.
"""
