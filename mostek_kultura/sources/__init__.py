"""Source registry: config `type` -> parser class."""

from __future__ import annotations

from .antee_rss import AnteeRssSource
from .bajkazyl_program import BajkazylProgramSource
from .base import Source
from .bio_central import BioCentralSource
from .cinestar import CineStarSource
from .drak_program import DrakProgramSource
from .drupal_events import DrupalEventsSource
from .epo1_calendar import Epo1CalendarSource
from .epo1_exhibitions import Epo1ExhibitionsSource
from .galileo import GalileoSource
from .goout import GoOutSource
from .hkinfo_program import HkinfoProgramSource
from .josefa_events import JosefaEventsSource
from .klaster_hostinne import KlasterHostinneSource
from .klicperovo_program import KlicperovoProgramSource
from .koruna_program import KorunaProgramSource
from .kultura_novapaka import KulturaNovaPakaSource
from .lodzie import LodzieSource
from .manual import ManualSource
from .menu_music import MenuMusicSource
from .mojekino import MojekinoSource
from .naplavka_program import NaplavkaProgramSource
from .npu_events import NpuEventsSource
from .podzimni_sneni import PodzimniSneniSource
from .public4u import Public4uSource
from .sd_jilm import SdJilmSource
from .simcal_calendar import SimcalCalendarSource
from .trut_program import TrutProgramSource
from .uffo import UffoSource
from .vismo import VismoSource
from .vismo6 import Vismo6Source
from .webnode_program import WebnodeProgramSource

REGISTRY: dict[str, type[Source]] = {
    "galileo": GalileoSource,
    "antee_rss": AnteeRssSource,
    "bio_central": BioCentralSource,
    "bajkazyl_program": BajkazylProgramSource,
    "cinestar": CineStarSource,
    "public4u": Public4uSource,
    "podzimni_sneni": PodzimniSneniSource,
    "goout": GoOutSource,
    "hkinfo_program": HkinfoProgramSource,
    "drupal_events": DrupalEventsSource,
    "drak_program": DrakProgramSource,
    "lodzie_program": LodzieSource,
    "npu_events": NpuEventsSource,
    "josefa_events": JosefaEventsSource,
    "klicperovo_program": KlicperovoProgramSource,
    "vismo": VismoSource,
    "vismo6": Vismo6Source,
    "kultura_novapaka": KulturaNovaPakaSource,
    "uffo": UffoSource,
    "sd_jilm": SdJilmSource,
    "manual": ManualSource,
    "menu_music": MenuMusicSource,
    "mojekino": MojekinoSource,
    "naplavka_program": NaplavkaProgramSource,
    "epo1_calendar": Epo1CalendarSource,
    "epo1_exhibitions": Epo1ExhibitionsSource,
    "webnode_program": WebnodeProgramSource,
    "koruna_program": KorunaProgramSource,
    "simcal_calendar": SimcalCalendarSource,
    "klaster_hostinne": KlasterHostinneSource,
    "trut_program": TrutProgramSource,
}


def make_source(cfg) -> Source:
    try:
        cls = REGISTRY[cfg.type]
    except KeyError as e:
        raise ValueError(f"unknown source type '{cfg.type}' for source '{cfg.name}'") from e
    return cls(cfg)
