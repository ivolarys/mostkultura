from dataclasses import replace

from mostek_kultura.config import Place
from mostek_kultura.render import build_sources_page


def test_sources_czech_city_order_does_not_change_config(cfg):
    before = [p.name for p in cfg.places]
    groups = build_sources_page([], cfg, [])['groups']
    assert [g['place'] for g in groups] == [
        'Bílá Třemešná', 'Borovnice', 'Dolní Brusnice', 'Dvůr Králové nad Labem',
        'Horní Brusnice', 'Hořice', 'Hostinné', 'Hradec Králové', 'Choustníkovo Hradiště',
        'Jaroměř', 'Jičín', 'Jilemnice', 'Josefov', 'Kuks', 'Lázně Bělohrad', 'Mostek', 'Nemojov',
        'Nová Paka', 'Pecka', 'Trutnov', 'Turnov', 'Vítězná', 'Vrchlabí',
        'Zvičina', 'Žireč',
    ]
    assert [p.name for p in cfg.places] == before


def test_czech_digraph_and_accented_letters(cfg):
    places = ['Žatec', 'Zlín', 'Šumperk', 'Svitavy', 'Říčany', 'Rakovník',
              'Chrudim', 'Ivančice', 'Hradec', 'Čáslav', 'Cvikov', 'Ábelov', 'Adamov']
    custom = replace(cfg, places=[Place(name) for name in places])
    assert [g['place'] for g in build_sources_page([], custom, [])['groups']] == [
        'Ábelov', 'Adamov', 'Cvikov', 'Čáslav', 'Hradec', 'Chrudim', 'Ivančice',
        'Rakovník', 'Říčany', 'Svitavy', 'Šumperk', 'Zlín', 'Žatec',
    ]


def test_lodzie_source_is_in_jicin_group(cfg):
    data = build_sources_page([], cfg, [])
    jicin = next(g for g in data['groups'] if g['place'] == 'Jičín')
    assert {'jicin', 'valdstejnska-lodzie'} <= {s['name'] for s in jicin['sources']}
    assert all(g['place'] != 'Valdštejnská lodžie' for g in data['groups'])
