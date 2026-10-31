"""scripts/textclean.py: one cleaner for every source (docs/PROBLEMS.md group 1, 2 Oct 2026)."""
import textclean as T
from lang_band import hard_drop


def clean(s):
    t = T.html_to_text(s)
    assert T.leftovers(t) == {}, T.leftovers(t)
    return t


def test_escaped_html_from_greenhouse_is_decoded_then_stripped():
    # Greenhouse sends its HTML entity-escaped. The old strip removed tags first and decoded second,
    # so every Greenhouse description kept its markup.
    raw = "&lt;p&gt;&lt;strong&gt;About the team:&lt;/strong&gt;&lt;/p&gt; &lt;ul&gt;&lt;li&gt;PyTorch &amp;amp; ONNX&lt;/li&gt;&lt;/ul&gt;"
    assert clean(raw) == "About the team:\n• PyTorch & ONNX"


def test_list_under_a_heading_keeps_its_shape_baehrbots():
    # docs/PROBLEMS.md 1.6. Flattened, this read "Sehr gute Englischkenntnisse und Deutschkenntnisse" and
    # the job was dropped on German. German is the last item under "Ein Plus".
    raw = ("<h3>Dein Profil</h3><ul><li>Erfahrung mit LLM-APIs</li><li>Sehr gute Englischkenntnisse</li></ul>"
           "<h3>Ein Plus</h3><ul><li>Erfahrung mit n8n</li><li>Deutschkenntnisse</li></ul>")
    t = clean(raw)
    assert t.split("\n") == ["Dein Profil", "• Erfahrung mit LLM-APIs", "• Sehr gute Englischkenntnisse", "",
                             "Ein Plus", "• Erfahrung mit n8n", "• Deutschkenntnisse"]
    assert hard_drop(t) is None


def test_a_bullet_list_is_one_requirement_per_line_akkodis():
    # docs/PROBLEMS.md 3.4: a bullet list used to be one sentence over 220 characters, which hard_drop skips.
    raw = "<ul>" + "".join("<li>%s</li>" % x for x in [
        "Abgeschlossenes Studium der Informatik, Elektrotechnik oder vergleichbar",
        "Mehrjährige Erfahrung in Machine Learning und Messtechnik in der Automobilindustrie",
        "Sehr gute Kenntnisse in Python, PyTorch und MATLAB",
        "Verhandlungssichere Deutsch- und Englischkenntnisse in Wort und Schrift"]) + "</ul>"
    assert hard_drop(clean(raw)) == "Verhandlungssichere Deutsch- und Englischkenntnisse in Wort und Schrift"


def test_inline_tags_add_no_space():
    assert clean("<p>We use <b>PyTorch</b>, <i>ONNX</i> and G<span>reat</span> tools.</p>") == \
        "We use PyTorch, ONNX and Great tools."


def test_script_style_and_comments_are_removed():
    raw = "<style>p{color:red}</style><p>Text</p><script>var a='<p>no</p>';</script><!-- hidden --><p>More</p>"
    assert clean(raw) == "Text\nMore"


def test_an_unclosed_skip_tag_does_not_swallow_the_posting():
    assert "Requirements" in clean("<p>Intro</p><button>Apply<p>Requirements: Python</p>")


def test_plain_text_keeps_its_own_line_breaks():
    # The Bundesagentur sends plain text. It was flattened to one line.
    raw = "Ihre Aufgaben:\r\n- Modelle trainieren\r\n- Pipelines bauen\r\n\r\n\r\n\r\nIhr Profil:\r\n· Python"
    assert clean(raw) == "Ihre Aufgaben:\n- Modelle trainieren\n- Pipelines bauen\n\nIhr Profil:\n• Python"


def test_entities_spaces_and_invisible_characters():
    raw = "<p>M&uuml;nchen&nbsp;&ndash;&nbsp;Gehalt&#8239;70.000&nbsp;&euro; ​und­ mehr</p>"
    assert clean(raw) == "München – Gehalt 70.000 € und mehr"


def test_an_entity_escaped_three_times():
    assert clean("<p>ventures &amp;amp;amp; accilium</p>") == "ventures & accilium"


def test_cdata_and_table():
    assert clean("<![CDATA[<table><tr><td>Level</td><td>B1</td></tr><tr><td>Ort</td><td>Berlin</td></tr></table>]]>") == \
        "Level B1\nOrt Berlin"


def test_nothing_is_cut():
    raw = "<p>" + "</p><p>".join("Sentence number %d about the work." % i for i in range(5000)) + "</p><p>German C1 required.</p>"
    t = clean(raw)
    assert len(t) > 150000 and t.endswith("German C1 required.")


def test_text_that_mentions_a_tag_is_left_alone():
    assert clean("We compare a < b and write C++ templates like vector&lt;int&gt;.") == \
        "We compare a < b and write C++ templates like vector<int>."


def test_join_html_keeps_every_field_in_order():
    # Lever: the requirements are in `lists`, the closing section in `additional`.
    h = T.join_html("Intro line one\nIntro line two", ("Requirements", "<li>Python</li><li>German is a plus</li>"),
                    ("Empty", ""), None, "<p>Closing</p>")
    assert clean(h) == "Intro line one\nIntro line two\n\nRequirements\n• Python\n• German is a plus\nClosing"


def test_empty_and_garbage_input():
    assert T.html_to_text(None) == "" and T.html_to_text("") == "" and T.html_to_text("   \n ") == ""
    assert T.html_to_text("<p>") == "" and T.html_to_text(12345) == "12345"


def test_leftovers_reports_a_dirty_text():
    assert set(T.leftovers("<p>Hi</p> &amp;  x")) == {"tags", "entities", "double_space"}
