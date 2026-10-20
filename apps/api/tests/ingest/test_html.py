"""The HTML reader on excerpts shaped like each publisher's files (markup as served or cut
on 2026-10-19, statute text shortened)."""

from __future__ import annotations

import pytest

from plumbline.ingest.html import HtmlError, decode, profile_for, to_markdown

FLORIDA = "https://www.leg.state.fl.us/statutes/index.cfm?App_mode=Display_Statute"
COLOMBIA = "https://www.secretariasenado.gov.co/senado/basedoc/ley_0820_2003.html"

# Lane B commits Florida's statute markup cut out of its page: no container, no charset.
FLORIDA_CUT = """<div class="Part"><div class="PartTitle">
  <div class="PartNumber">PART II</div><span class="PartTitle">RESIDENTIAL TENANCIES</span></div>
<div class="CatchlineIndex"><div class="IndexItem"><span class="SectionNumber">83.49&#x2003;</span>
  <span class="Catchline">Deposit money or advance rent.</span></div></div>
<div class="Section"><sup><a href="#1">1</a></sup><span class="SectionNumber">83.49&#x2003;</span><span class="Catchline"><span
  class="CatchlineText">Deposit money or advance rent; duty of landlord and tenant.</span><span
  class="EmDash">&#x2014;</span></span><div class="Subsection"><span class="Number">(1)</span>
  <span class="Text Intro Justify">Whenever money is deposited or advanced by a tenant:</span>
  <div class="Paragraph"><span class="Number">(a)</span> <span class="Text">The landlord shall
  hold the total amount.</span></div></div>
<div class="History"><span class="HistoryTitle">History.</span><span
  class="EmDash">&#x2014;</span><span class="HistoryText">s. 2, ch. 73-330.</span></div>
<div class="Note"><sup><a name="1">1</a></sup><span class="NoteTitle">Note.</span><span
  class="EmDash">&#x2014;</span><span class="Text">Former s. 83.261.</span></div></div>
</div>"""

# Colombia's page: Latin-1 declared, Windows-1252 in fact (the curly quotes); the container
# opened twice, the first one never closed; struck-out words the Court declared void.
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
<p><a class="bookmarkaj" name="37">ART&Iacute;CULO 37. PAGO DE SERVICIOS, <S>COSAS O USOS
CONEXOS </S>.</A> <S><span class="b_aj">Cualquiera que fuere la causal invocada</span></S>,
<U>el demandado deber&aacute; presentar la prueba</U> del pago.</p>
<p>Inciso vigente. <S>Inciso tachado
<p>que sigue tachado</S> y texto vigente.</p>
<div id="logo_aj"><div>Avance Jur&iacute;dico</div></div>
</BODY></html>"""


def test_a_florida_cut_is_read_whole_without_its_index_or_footnote_marks() -> None:
    markdown = to_markdown(decode(FLORIDA_CUT.encode()), profile_for(FLORIDA))
    assert markdown.split("\n\n") == [
        "PART II",
        "RESIDENTIAL TENANCIES",
        "83.49 Deposit money or advance rent; duty of landlord and tenant.—",
        "(1) Whenever money is deposited or advanced by a tenant:",
        "(a) The landlord shall hold the total amount.",
        "History.—s. 2, ch. 73-330.",
        "Note.—Former s. 83.261.",
    ]


def test_the_colombian_page_is_read_as_windows_1252_in_spite_of_its_tag_soup() -> None:
    markdown = to_markdown(decode(COLOMBIA_PAGE.encode("cp1252")), profile_for(COLOMBIA))
    assert markdown.split("\n\n")[:3] == [
        "LEY 820 DE 2003",
        "ARTÍCULO 12. LUGAR PARA RECIBIR NOTIFICACIONES. En todo contrato de"
        " “arrendamiento” se indicará la dirección.",
        "<Inciso 3o. INEXEQUIBLE>",
    ]


def test_struck_out_words_stay_marked_as_struck() -> None:
    markdown = to_markdown(decode(COLOMBIA_PAGE.encode("cp1252")), profile_for(COLOMBIA))
    assert markdown.split("\n\n")[3:] == [
        "ARTÍCULO 37. PAGO DE SERVICIOS, ~~COSAS O USOS CONEXOS~~. ~~Cualquiera que fuere la"
        " causal invocada~~, el demandado deberá presentar la prueba del pago.",
        "Inciso vigente. ~~Inciso tachado~~",
        "~~que sigue tachado~~ y texto vigente.",
    ]


def test_an_unknown_site_is_refused() -> None:
    with pytest.raises(HtmlError, match=r"no HTML profile for www\.boe\.es"):
        profile_for("https://www.boe.es/buscar/act.php?id=BOE-A-1994-26003")


def test_a_page_without_the_container_is_refused() -> None:
    with pytest.raises(HtmlError, match="aj_data"):
        to_markdown("<html><body><p>Mantenimiento</p></body></html>", profile_for(COLOMBIA))


def test_bytes_that_are_not_the_declared_charset_are_refused() -> None:
    with pytest.raises(HtmlError, match="not valid utf-8"):
        decode(b'<meta charset="utf-8"><p>Art\xedculo</p>')


SENATE = "http://www.secretariasenado.gov.co/senado/basedoc"


def _senate_page(article: str, text: str) -> str:
    return (
        '<html><head><meta http-equiv="Content-Type" content="text/html; charset=ISO-8859-1" />'
        '</head><BODY><div id="aj_data">'
        f'<p><a class="bookmarkaj" name="{article}">ART&Iacute;CULO {article}.</a> {text}</p>'
        '<div><a class="caja_vja_encabezado" href="javascript:insRow1()">Jurisprudencia Vigencia'
        '</a></div><table id="Table1" class="caja_vja_v" cellPadding=10 width="100%"></table>'
        "</div></BODY></html>"
    )


def _senate_script(note: str) -> str:
    return (
        'function insRow1()\r\n{\r\nvar description = new Array();\r\ndescription[0] = "'
        f"<tbody><tr><td><p><span class='b_aj'>Corte Constitucional</span></p><p>{note}</p>"
        "</td></tr></tbody>\";\r\nvar z=document.getElementById('Table1').rows[0];\r\n}\r\n"
    )


def test_the_senates_notes_fill_the_boxes_of_their_own_page() -> None:
    # Lane B's file: each page, then the script that fills its boxes; numbering restarts.
    parts = [
        (
            f"{SENATE}/ley_0820_2003.html",
            _senate_page("12", "Las partes indicar&aacute;n la direcci&oacute;n."),
        ),
        (f"{SENATE}/js/ley_0820_2003.js", _senate_script("Inciso 3o. declarado INEXEQUIBLE.")),
        (
            f"{SENATE}/ley_0820_2003_pr001.html",
            _senate_page("40", "Los contratos se registrar&aacute;n."),
        ),
        (f"{SENATE}/js/ley_0820_2003_pr001.js", _senate_script(r"Declarado \"EXEQUIBLE\".")),
    ]
    joined = "".join(f"<!-- plumbline part: {url} -->\n{body}\n" for url, body in parts)
    markdown = to_markdown(decode(joined.encode("cp1252")), profile_for(COLOMBIA))
    assert markdown.split("\n\n") == [
        "ARTÍCULO 12. Las partes indicarán la dirección.",
        "> Corte Constitucional",
        "> Inciso 3o. declarado INEXEQUIBLE.",
        "ARTÍCULO 40. Los contratos se registrarán.",
        "> Corte Constitucional",
        '> Declarado "EXEQUIBLE".',
    ]


def test_a_box_whose_script_has_no_note_is_an_error() -> None:
    parts = [
        (f"{SENATE}/ley_0820_2003.html", _senate_page("12", "Texto.")),
        (f"{SENATE}/js/ley_0820_2003.js", "function insRow1() { description[0]='changed'; }"),
    ]
    joined = "".join(f"<!-- plumbline part: {url} -->\n{body}\n" for url, body in parts)
    with pytest.raises(HtmlError, match=r"ley_0820_2003\.js has no note for box 1"):
        to_markdown(decode(joined.encode("cp1252")), profile_for(COLOMBIA))
