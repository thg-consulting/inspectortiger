from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Set

from inspectortiger.config import Config
from inspectortiger.inspector import Inspector
from inspectortiger.plugin import Plugin
from inspectortiger.utils import Group, logger

CORE_PLUGINS = Plugin.from_config(
    {"inspectortiger.plugins": ["context", "parentize", "general", "upgrade"]}
)


@dataclass
class Session:
    config: Config = field(default_factory=Config)
    plugins: Set[Plugin] = field(default_factory=set)

    def start(self):
        if self.config.load_core:
            self.load_plugins(*CORE_PLUGINS)
        self.load_plugins(*self.config.plugins)

    def load_plugin(self, plugin):
        if plugin not in self.config.blacklist.plugins:
            plugin.load()
            self.plugins.add(plugin)

    def load_plugins(self, *plugins):
        for plugin in plugins:
            self.load_plugin(plugin)

    def single_inspection(self, file):
        try:
            inspector = Inspector(file)
        except SyntaxError:
            logger.exception(f"Couldn't parse {file}")
            return {}
        else:
            return inspector.handle()

    def bulk_inspection(self, *files):
        mapper = ProcessPoolExecutor(self.config.workers).map
        return self.merge_inspections(mapper(self.single_inspection, files))

    def group_by(self, inspection, group):
        for plugin, reports in inspection.items():
            for report in reports:
                if report.code not in self.config.blacklist.codes:
                    if group is Group.PLUGIN:
                        yield plugin, asdict(report)
                    elif isinstance(group, Group):
                        yield getattr(report, group.name.lower()), {
                            "plugin": plugin,
                            **asdict(report),
                        }
                    else:
                        raise ValueError(f"Unsupported grouping, {group}.")

    def merge_inspections(self, inspections, group=Group.PLUGIN):
        all_reports = defaultdict(list)

        for inspection in inspections:
            for groupper, report in self.group_by(inspection, group):
                all_reports[groupper].append(report)

        return all_reports
