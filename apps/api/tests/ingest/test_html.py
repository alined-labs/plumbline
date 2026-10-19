"""The HTML reader on excerpts shaped like each publisher's pages (markup as served on
2026-10-19, statute text shortened)."""

from __future__ import annotations

import pytest

from plumbline.ingest.html import HtmlError, decode, profile_for, to_markdown

BOE = "https://www.boe.es/buscar/act.php?id=BOE-A-1994-26003"
FLORIDA = "https://www.leg.state.fl.us/statutes/index.cfm?App_mode=Display_Statute"
COLOMBIA = "https://www.secretariasenado.gov.co/senado/basedoc/ley_0820_2003.html"

BOE_PAGE = """<html><head><meta charset="utf-8"><title>BOE</title></head><body>
<div id="menu"><ul><li>Inicio</li></ul></div>
<div id="textoxslt">
<h3>Texto consolidado<span>: &laquo;publicada el 07/10/2026&raquo;</span></h3>
<div class="marcadores"><label>Ir a: </label>
  <ul id="lista-marcadores"><li><a href="#a9">Art&iacute;culo 9</a></li></ul></div>
<h4 class="capitulo_num">CAP&Iacute;TULO II</h4>
<div class="bloque" id="a9">
  <p class="bloque">[Bloque 14: #a9]</p>
  <form action="#"><input type="hidden" name="id"/><label>Jurisprudencia</label></form>
  <h5 class="articulo">Art&iacute;culo 9. Plazo m&iacute;nimo.</h5>
  <p class="parrafo">1. La duraci&oacute;n del arrendamiento
     ser&aacute; libremente pactada por las partes.</p>
  <blockquote>
    <p class="nota_pie">Se modifica por el art. 1.4 del Real Decreto-ley 7/2019.
      <a href="/buscar/act.php?id=BOE-A-2019-3108">Ref. BOE-A-2019-3108</a></p>
  </blockquote>
  <p class="linkSubir"><a href="#top">Subir</a></p>
</div>
</div>
<div id="pie">Agencia Estatal Bolet&iacute;n Oficial del Estado</div>
</body></html>"""

FLORIDA_PAGE = """<html><body><table><tr><td>Online Sunshine menu</td></tr></table>
<div id="statutes"><html><head><title>CHAPTER 83</title></head><body>
<div class="Chapter"><div class="Part"><div class="PartTitle">
  <div class="PartNumber">PART II</div><span class="PartTitle">RESIDENTIAL TENANCIES</span></div>
<div class="CatchlineIndex"><div class="IndexItem"><span class="SectionNumber">83.49&#x2003;</span>
  <span class="Catchline">Deposit money or advance rent.</span></div></div>
<div class="Section"><span class="SectionNumber">83.49&#x2003;</span><span class="Catchline"><span
  class="CatchlineText">Deposit money or advance rent; duty of landlord and tenant.</span><span
  class="EmDash">&#x2014;</span></span><div class="Subsection"><span class="Number">(1)</span>
  <span class="Text Intro Justify">Whenever money is deposited or advanced by a tenant:</span>
  <div class="Paragraph"><span class="Number">(a)</span> <span class="Text">The landlord shall
  hold the total amount.</span></div></div>
<div class="History"><span class="HistoryTitle">History.</span><span
  class="EmDash">&#x2014;</span><span class="HistoryText">s. 2, ch. 73-330.</span></div></div>
</div></div></body></html></div>
</body></html>"""

# Colombia's page: Latin-1 declared, Windows-1252 in fact (the curly quotes), and the
# container opened twice, the first one never closed.
COLOMBIA_PAGE = """<html><head><meta http-equiv="Content-Type" content="text/html; charset=ISO-8859-1" />
<script>function insRow4() {}</script></head>
<div id="aj_data"><div id="update_date"><div>&Uacute;ltima actualizaci&oacute;n: 15 de octubre</div></div>
<BODY><div id="aj_data"><div><a class="hlk_inicio" href="arbol/1000.html">Inicio</a></div>
<div id="selector_aj"><select><option>Ley 820</option></select></div>
<p style="text-align:center;"><a class=antsig href="ley_0820_2003_pr001.html">Siguiente</a></p>
<p class="centrado">LEY 820 DE 2003</p>
<div><a class="caja_vja_encabezado_c" href="javascript:insRow1()">Resumen de Notas de Vigencia</a></div>
<table id="Table1" class="caja_vja_v"></table>
<p><a class="bookmarkaj" name="12">ART&Iacute;CULO 12. LUGAR PARA RECIBIR NOTIFICACIONES.</A>
En todo contrato de “arrendamiento” se indicar&aacute; la direcci&oacute;n.</p>
<p>&lt;Inciso 3o. INEXEQUIBLE&gt;</p>
<div><a class="caja_vja_encabezado" href="javascript:insRow4()">Jurisprudencia Vigencia</a></div>
<table id="Table4" class="caja_vja_v" cellPadding=10 width="100%"></table>
<div id="logo_aj"><div>Avance Jur&iacute;dico</div></div>
</BODY></html>"""


def test_the_boe_page_keeps_headings_paragraphs_and_amendment_notes() -> None:
    markdown = to_markdown(decode(BOE_PAGE.encode()), profile_for(BOE))
    assert markdown.split("\n\n") == [
        "### Texto consolidado: «publicada el 07/10/2026»",
        "#### CAPÍTULO II",
        "##### Artículo 9. Plazo mínimo.",
        "1. La duración del arrendamiento será libremente pactada por las partes.",
        "> Se modifica por el art. 1.4 del Real Decreto-ley 7/2019. Ref. BOE-A-2019-3108",
    ]


def test_the_florida_page_keeps_sections_and_history_and_drops_the_index() -> None:
    markdown = to_markdown(decode(FLORIDA_PAGE.encode()), profile_for(FLORIDA))
    assert markdown.split("\n\n") == [
        "PART II",
        "RESIDENTIAL TENANCIES",
        "83.49 Deposit money or advance rent; duty of landlord and tenant.—",
        "(1) Whenever money is deposited or advanced by a tenant:",
        "(a) The landlord shall hold the total amount.",
        "History.—s. 2, ch. 73-330.",
    ]


def test_the_colombian_page_is_read_as_windows_1252_in_spite_of_its_tag_soup() -> None:
    markdown = to_markdown(decode(COLOMBIA_PAGE.encode("cp1252")), profile_for(COLOMBIA))
    assert markdown.split("\n\n") == [
        "LEY 820 DE 2003",
        "ARTÍCULO 12. LUGAR PARA RECIBIR NOTIFICACIONES. En todo contrato de"
        " “arrendamiento” se indicará la dirección.",
        "<Inciso 3o. INEXEQUIBLE>",
    ]


def test_an_unknown_site_is_refused() -> None:
    with pytest.raises(HtmlError, match=r"no HTML profile for example\.org"):
        profile_for("https://example.org/law.html")


def test_a_page_without_the_container_is_refused() -> None:
    with pytest.raises(HtmlError, match="textoxslt"):
        to_markdown("<html><body><p>Mantenimiento</p></body></html>", profile_for(BOE))


def test_bytes_that_are_not_the_declared_charset_are_refused() -> None:
    with pytest.raises(HtmlError, match="not valid utf-8"):
        decode(b'<meta charset="utf-8"><p>Art\xedculo</p>')
