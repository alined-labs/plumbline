"""The BOE open-data reader: a record shaped like the BOE's (structure as served on
2026-10-13, text shortened), and the two committed Spanish records."""

from __future__ import annotations

import re

import pytest

from plumbline.ingest.boe import BoeError, to_markdown
from plumbline.settings import ROOT

RECORD = """<?xml version="1.0" encoding="utf-8"?>
<response><status><code>200</code></status><data>
<metadatos><fecha_actualizacion>20261013T112227Z</fecha_actualizacion></metadatos>
<texto>
  <bloque id="ci" tipo="encabezado" titulo="CAPÍTULO I">
    <version id_norma="BOE-A-1994-26003" fecha_publicacion="19941125" fecha_vigencia="19950101">
      <p class="capitulo_num">CAPITULO I</p>
    </version>
    <version id_norma="BOE-A-2013-5941" fecha_publicacion="20130605" fecha_vigencia="20130606">
      <p class="capitulo_num">CAPÍTULO I</p>
      <p class="capitulo_tit">Disposiciones generales</p>
    </version>
  </bloque>
  <bloque id="a9" tipo="precepto" titulo="Artículo 9">
    <version id_norma="BOE-A-1994-26003" fecha_publicacion="19941125" fecha_vigencia="19950101">
      <p class="articulo">Artículo 9. Plazo mínimo.</p>
      <p class="parrafo">1. Si ésta fuera inferior a <strong>cinco</strong> años, se prorrogará.</p>
    </version>
    <version id_norma="BOE-A-2019-3108" fecha_publicacion="20190305" fecha_vigencia="">
      <p class="articulo">Artículo 9. Plazo mínimo.</p>
      <p class="parrafo">1. Si esta fuera inferior a cinco años, o a siete si el arrendador
         fuese persona jurídica, se prorrogará.</p>
      <table class="tabla"><tbody><tr><th>Plazo</th><th>Años</th></tr>
        <tr><td>Persona física</td><td>5</td></tr></tbody></table>
      <blockquote caduca="" class="siempreSeVe">
        <p class="parrafo">Téngase en cuenta que, con efectos de 15 de noviembre de 2026, se modifica.</p>
      </blockquote>
      <blockquote>
        <p class="nota_pie">Se modifica por el art. 1.4 del Real Decreto-ley 7/2019.
          <a class="refPost">Ref. BOE-A-2019-3108#ap</a></p>
      </blockquote>
      <p> </p>
    </version>
  </bloque>
</texto></data></response>""".encode()


def test_each_version_of_an_article_follows_its_marker() -> None:
    assert to_markdown(RECORD).split("\n\n") == [
        "#### CAPÍTULO I",
        "#### Disposiciones generales",
        "<!-- plumbline:version block=a9 norm=BOE-A-1994-26003 published=1994-11-25"
        " effective=1995-01-01 -->",
        "##### Artículo 9. Plazo mínimo.",
        "1. Si ésta fuera inferior a cinco años, se prorrogará.",
        "<!-- plumbline:version block=a9 norm=BOE-A-2019-3108 published=2019-03-05 effective= -->",
        "##### Artículo 9. Plazo mínimo.",
        "1. Si esta fuera inferior a cinco años, o a siete si el arrendador fuese persona"
        " jurídica, se prorrogará.",
        "Plazo | Años",
        "Persona física | 5",
        "> Téngase en cuenta que, con efectos de 15 de noviembre de 2026, se modifica.",
        "> Se modifica por el art. 1.4 del Real Decreto-ley 7/2019. Ref. BOE-A-2019-3108#ap",
    ]


@pytest.mark.parametrize(
    ("record", "error"),
    [
        (b"<response><data>", "not well-formed"),
        (b"<response><data><metadatos/></data></response>", "no data/texto"),
        (
            b'<response><data><texto><bloque id="a1" tipo="precepto">'
            b'<version fecha_publicacion="1994-11-25"/></bloque></texto></data></response>',
            "unexpected BOE date",
        ),
    ],
)
def test_a_record_the_reader_cannot_vouch_for_is_refused(record: bytes, error: str) -> None:
    with pytest.raises(BoeError, match=error):
        to_markdown(record)


@pytest.mark.parametrize(
    ("source", "versions", "articles"),
    [("es-lau-boe-2026-10-13", 233, 53), ("es-lph-boe-2026-10-05", 94, 24)],
)
def test_the_committed_records_keep_every_version(
    source: str, versions: int, articles: int
) -> None:
    markdown = to_markdown((ROOT / "data" / "corpus" / "raw" / f"{source}.xml").read_bytes())
    markers = re.findall(r"^<!-- plumbline:version block=(\S+) ", markdown, re.MULTILINE)
    # The LAU numbers its articles in figures ("Artículo 9 bis."), the LPH in words
    # ("Artículo veintiuno.").
    headings = set(re.findall(r"^##### (Artículo [^.]+)\.", markdown, re.MULTILINE))
    assert (len(markers), len(headings)) == (versions, articles)
