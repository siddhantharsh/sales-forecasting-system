#!/usr/bin/env python3
"""Builds sales_forecasting_dashboard.twbx from the CSV files in this folder.

Usage: python build_workbook.py [path/to/twb_2026.1.0.xsd]
The optional XSD (from github.com/tableau/tableau-document-schemas) is used to
validate the generated workbook XML before it is packaged.
"""
import sys
import uuid
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

HERE = Path(__file__).parent
TWB_NAME = "sales_forecasting_dashboard"

# ── Data sources ──────────────────────────────────────────────────────────────
# (csv file, caption, [(column, csv datatype)], dimension columns that are nominal)
SOURCES = {
    "kpi": ("kpi_tiles.csv", "KPI tiles",
            [("total_sales", "real"), ("avg_daily_sales", "real"),
             ("promotion_lift_pct", "real"), ("best_model_mape_pct", "real")]),
    "holdout": ("holdout_long.csv", "Holdout forecasts",
                [("date", "date"), ("model", "string"), ("sales", "real")]),
    "dow": ("sales_by_day_of_week.csv", "Sales by day of week",
            [("day_num", "integer"), ("day", "string"), ("avg_daily_sales", "real")]),
    "month": ("sales_by_month.csv", "Sales by month",
              [("month_num", "integer"), ("month", "string"), ("avg_daily_sales", "real")]),
    "family": ("sales_by_family.csv", "Sales by family",
               [("family", "string"), ("sales", "real")]),
    "store": ("sales_by_store.csv", "Sales by store",
              [("store", "string"), ("store_nbr", "integer"), ("city", "string"),
               ("state", "string"), ("type", "string"), ("sales", "real")]),
}
DS = {k: f"federated.{i:02d}0sales0forecasting0tableau0{k:<5}".replace(" ", "x")
      for i, k in enumerate(SOURCES, start=1)}
CONN = {k: f"textscan.{i:02d}0sales0forecasting0tableau0{k:<5}".replace(" ", "x")
        for i, k in enumerate(SOURCES, start=1)}

# Model colours (data-viz categorical order; Actual is a neutral dark grey)
PALETTE = [
    ("Actual", "#3b3b3a"),
    ("Random forest (MAPE 5.7%)", "#2a78d6"),
    ("Prophet (MAPE 7.4%)", "#eb6834"),
    ("Seasonal naive (MAPE 10.1%)", "#1baf7a"),
]
BAR = "#2a78d6"


def q(s):
    return quoteattr(s)


def simple_id(label):
    return f"<simple-id uuid='{{{str(uuid.uuid5(uuid.NAMESPACE_URL, 'sales-forecasting/' + label)).upper()}}}' />"


def fld(ds, name):
    return f"[{DS[ds]}].[{name}]"


def datasource(key):
    filename, caption, cols = SOURCES[key]
    col_xml = "\n".join(
        f"            <column datatype='{t}' name={q(n)} ordinal='{i}' />"
        for i, (n, t) in enumerate(cols))
    defs = []
    for n, t in cols:
        if t in ("string", "date"):
            role, typ = "dimension", ("ordinal" if t == "date" else "nominal")
        elif n in ("store_nbr", "day_num", "month_num"):
            role, typ = "measure", "quantitative"
        else:
            role, typ = "measure", "quantitative"
        defs.append(f"      <column datatype='{t}' name='[{n}]' role='{role}' type='{typ}' />")
    style = ""
    if key == "holdout":
        maps = "\n".join(
            f"            <map to='{c}'>\n              <bucket>&quot;{escape(m)}&quot;</bucket>\n            </map>"
            for m, c in PALETTE)
        style = (f"      <style>\n        <style-rule element='mark'>\n"
                 f"          <encoding attr='color' field='[none:model:nk]' type='palette'>\n{maps}\n"
                 f"          </encoding>\n        </style-rule>\n      </style>\n")
    return f"""    <datasource caption={q(caption)} inline='true' name='{DS[key]}' version='26.1'>
      <connection class='federated'>
        <named-connections>
          <named-connection caption={q(caption)} name='{CONN[key]}'>
            <connection class='textscan' directory='Data' filename={q(filename)} password='' server='' />
          </named-connection>
        </named-connections>
        <relation connection='{CONN[key]}' name={q(filename)} table={q(f'[{filename[:-4]}#csv]')} type='table'>
          <columns character-set='UTF-8' header='yes' locale='en_US' separator=','>
{col_xml}
          </columns>
        </relation>
      </connection>
      <aliases enabled='yes' />
{chr(10).join(defs)}
{style}    </datasource>"""


# ── Worksheets ────────────────────────────────────────────────────────────────
def title_xml(text, size=12):
    return (f"      <layout-options>\n        <title>\n          <formatted-text>\n"
            f"            <run bold='true' fontsize='{size}'>{escape(text)}</run>\n"
            f"          </formatted-text>\n        </title>\n      </layout-options>\n")


def worksheet(name, key, deps, view_extra, mark, encodings, pane_style, rows, cols,
              title, title_size=12, table_style=""):
    caption = SOURCES[key][1]
    return f"""    <worksheet name={q(name)}>
{title_xml(title, title_size)}      <table>
        <view>
          <datasources>
            <datasource caption={q(caption)} name='{DS[key]}' />
          </datasources>
          <datasource-dependencies datasource='{DS[key]}'>
{deps}
          </datasource-dependencies>
{view_extra}          <aggregation value='true' />
        </view>
        <style>
{table_style}        </style>
        <panes>
          <pane selection-relaxation-option='selection-relaxation-allow'>
            <view>
              <breakdown value='auto' />
            </view>
            <mark class='{mark}' />
{encodings}            <style>
{pane_style}            </style>
          </pane>
        </panes>
        <rows>{rows}</rows>
        <cols>{cols}</cols>
      </table>
      {simple_id(name)}
    </worksheet>"""


def inst(col, deriv, name, typ):
    return (f"            <column-instance column='[{col}]' derivation='{deriv}' "
            f"name='[{name}]' pivot='key' type='{typ}' />")


def coldef(col, dtype, role, typ):
    return (f"            <column datatype='{dtype}' name='[{col}]' role='{role}' type='{typ}' />")


def kpi_sheet(name, col, fmt, title):
    key = "kpi"
    deps = "\n".join([coldef(col, "real", "measure", "quantitative"),
                      inst(col, "Sum", f"sum:{col}:qk", "quantitative")])
    f = fld(key, f"sum:{col}:qk")
    enc = f"            <encodings>\n              <text column='{f}' />\n            </encodings>\n"
    style = (f"              <style-rule element='mark'>\n"
             f"                <format attr='mark-labels-show' value='true' />\n"
             f"              </style-rule>\n"
             f"              <style-rule element='label'>\n"
             f"                <format attr='font-size' value='34' />\n"
             f"                <format attr='font-weight' value='bold' />\n"
             f"                <format attr='text-align' value='center' />\n"
             f"                <format attr='text-format' field='{f}' value={q(fmt)} />\n"
             f"              </style-rule>\n")
    return worksheet(name, key, deps, "", "Automatic", enc, style, "", "", title, 11)


def holdout_sheet():
    key = "holdout"
    deps = "\n".join([
        coldef("date", "date", "dimension", "ordinal"),
        coldef("model", "string", "dimension", "nominal"),
        coldef("sales", "real", "measure", "quantitative"),
        inst("date", "Day-Trunc", "tdy:date:qk", "quantitative"),
        inst("model", "None", "none:model:nk", "nominal"),
        inst("sales", "Sum", "sum:sales:qk", "quantitative"),
    ])
    enc = f"            <encodings>\n              <color column='{fld(key, 'none:model:nk')}' />\n            </encodings>\n"
    style = ("              <style-rule element='mark'>\n"
             "                <format attr='mark-labels-show' value='false' />\n"
             "              </style-rule>\n")
    table_style = (f"          <style-rule element='axis'>\n"
                   f"            <format attr='text-format' field='{fld(key, 'sum:sales:qk')}' scope='rows' value='$#,##0,&quot;K&quot;' />\n"
                   f"          </style-rule>\n")
    return worksheet("Actual vs forecast", key, deps, "", "Line", enc, style,
                     fld(key, "sum:sales:qk"), fld(key, "tdy:date:qk"),
                     "Actual vs forecast: 90-day holdout (daily sales, $K)", 14,
                     table_style)


def column_chart(name, key, cat, num_col, order_col, title):
    deps = "\n".join([
        coldef(cat, "string", "dimension", "nominal"),
        coldef(num_col, "real", "measure", "quantitative"),
        coldef(order_col, "integer", "measure", "quantitative"),
        inst(cat, "None", f"none:{cat}:nk", "nominal"),
        inst(num_col, "Sum", f"sum:{num_col}:qk", "quantitative"),
        inst(order_col, "Min", f"min:{order_col}:qk", "quantitative"),
    ])
    sort = (f"          <computed-sort column='{fld(key, f'none:{cat}:nk')}' direction='ASC' "
            f"using='{fld(key, f'min:{order_col}:qk')}' />\n")
    enc = f"            <encodings>\n              <text column='{fld(key, f'sum:{num_col}:qk')}' />\n            </encodings>\n"
    style = (f"              <style-rule element='mark'>\n"
             f"                <format attr='mark-color' value='{BAR}' />\n"
             f"                <format attr='mark-labels-show' value='true' />\n"
             f"              </style-rule>\n"
             f"              <style-rule element='label'>\n"
             f"                <format attr='text-format' field='{fld(key, f'sum:{num_col}:qk')}' value='$#,##0,&quot;K&quot;' />\n"
             f"              </style-rule>\n")
    return worksheet(name, key, deps, sort, "Bar", enc, style,
                     fld(key, f"sum:{num_col}:qk"), fld(key, f"none:{cat}:nk"), title)


def bar_chart(name, key, cat, num_col, title, extra_deps=(), view_extra=""):
    deps = "\n".join([
        coldef(cat, "string", "dimension", "nominal"),
        coldef(num_col, "real", "measure", "quantitative"),
        inst(cat, "None", f"none:{cat}:nk", "nominal"),
        inst(num_col, "Sum", f"sum:{num_col}:qk", "quantitative"),
        *extra_deps,
    ])
    sort = (f"          <computed-sort column='{fld(key, f'none:{cat}:nk')}' direction='DESC' "
            f"using='{fld(key, f'sum:{num_col}:qk')}' />\n")
    enc = f"            <encodings>\n              <text column='{fld(key, f'sum:{num_col}:qk')}' />\n            </encodings>\n"
    style = (f"              <style-rule element='mark'>\n"
             f"                <format attr='mark-color' value='{BAR}' />\n"
             f"                <format attr='mark-labels-show' value='true' />\n"
             f"              </style-rule>\n"
             f"              <style-rule element='label'>\n"
             f"                <format attr='text-format' field='{fld(key, f'sum:{num_col}:qk')}' value='$#,##0.0,,&quot;M&quot;' />\n"
             f"              </style-rule>\n")
    return worksheet(name, key, deps, view_extra + sort, "Bar", enc, style,
                     fld(key, f"none:{cat}:nk"), fld(key, f"sum:{num_col}:qk"), title)


def store_sheet():
    key = "store"
    state_inst = inst("state", "None", "none:state:nk", "nominal")
    flt = (f"          <filter class='categorical' column='{fld(key, 'none:state:nk')}'>\n"
           f"            <groupfilter function='level-members' level='[none:state:nk]' />\n"
           f"          </filter>\n")
    return bar_chart("Store ranking", key, "store", "sales",
                     "Store ranking by total sales (filter by state)",
                     extra_deps=[coldef("state", "string", "dimension", "nominal"), state_inst],
                     view_extra=flt)


# ── Dashboard ─────────────────────────────────────────────────────────────────
ZSTYLE = ("<zone-style><format attr='border-color' value='#000000' />"
          "<format attr='border-style' value='none' /><format attr='border-width' value='0' />"
          "<format attr='margin' value='4' /></zone-style>")

_zid = [10]


def zid():
    _zid[0] += 1
    return _zid[0]


def sheet_zone(name, x, y, w, h, extra=""):
    return (f"        <zone h='{h}' id='{zid()}' name={q(name)} w='{w}' x='{x}' y='{y}'{extra}>"
            f"{ZSTYLE}</zone>")


def text_zone(runs, x, y, w, h):
    body = "".join(runs)
    return (f"        <zone h='{h}' id='{zid()}' type-v2='text' w='{w}' x='{x}' y='{y}'>"
            f"<formatted-text>{body}</formatted-text>{ZSTYLE}</zone>")


def run(text, size=12, bold=False, color="#0b0b0b"):
    b = " bold='true'" if bold else ""
    return f"<run{b} fontcolor='{color}' fontsize='{size}'>{escape(text)}</run>"


NL = "<run>&#10;</run>"

FINDINGS = [
    ("Forecast accuracy", "Random forest 5.7% MAPE vs 10.1% for the seasonal naive baseline "
                          "(43% lower error); Prophet 7.4%; SARIMA 7.7%."),
    ("Weekly pattern", "Sunday is the strongest day ($825K average), Thursday the weakest ($505K)."),
    ("Yearly pattern", "December peaks (about $809K per day); February is lowest (about $572K)."),
    ("Growth", "Average daily sales in the latest year ($841K) are 2.2x the first year ($385K)."),
    ("Promotions", "Days with promotions averaged 70% higher sales; this is not a causal estimate "
                   "because promotions and the sales trend both rise over time."),
]


def dashboard():
    zones = []
    zones.append(text_zone([run("Retail sales forecasting dashboard", 22, True),
                            NL, run("Kaggle Store Sales (Favorita): 54 stores, 33 product families, "
                                    "daily totals, Jan 2013 to Aug 2017", 12, False, "#52514e")],
                           0, 0, 100000, 5000))
    for i, n in enumerate(["KPI total sales", "KPI average daily sales",
                           "KPI promotion lift", "KPI best model MAPE"]):
        zones.append(sheet_zone(n, i * 25000, 5500, 24500, 9000))
    zones.append(sheet_zone("Actual vs forecast", 0, 15000, 60500, 30000))
    zones.append(sheet_zone("Sales by day of week", 0, 46000, 30000, 24000))
    zones.append(sheet_zone("Sales by month", 30500, 46000, 30000, 24000))
    runs = [run("What the data shows", 14, True), NL]
    for head, body in FINDINGS:
        runs += [NL, run(head + ": ", 11, True), run(body, 11)]
    zones.append(text_zone(runs, 0, 71000, 60500, 25000))
    zones.append(sheet_zone("Top product families", 61500, 15000, 38500, 39000))
    zones.append(sheet_zone(
        "Store ranking", 61500, 55000, 38500, 3500,
        extra=f" mode='checkdropdown' param='{fld('store', 'none:state:nk')}' type-v2='filter'"))
    zones.append(sheet_zone("Store ranking", 61500, 58500, 38500, 37500))
    zones.append(text_zone(
        [run("Evaluation: single 90-day holdout (2017-05-18 to 2017-08-15), not walk-forward "
             "validation. The random forest forecast is recursive over all 90 days but uses the "
             "actual promotion and holiday flags for that period.", 10, False, "#52514e")],
        0, 96500, 100000, 3500))
    return f"""    <dashboard name='Retail sales forecasting dashboard'>
      <style />
      <size maxheight='1700' maxwidth='1500' minheight='1700' minwidth='1500' sizing-mode='fixed' />
      <zones>
        <zone h='100000' id='4' type-v2='layout-basic' w='100000' x='0' y='0'>
{chr(10).join(zones)}
          <zone-style>
            <format attr='border-color' value='#000000' />
            <format attr='border-style' value='none' />
            <format attr='border-width' value='0' />
            <format attr='margin' value='8' />
          </zone-style>
        </zone>
      </zones>
      {simple_id('dashboard')}
    </dashboard>"""


def build_twb():
    sheets = [
        kpi_sheet("KPI total sales", "total_sales", "$#,##0.0,,\"M\"", "Total sales"),
        kpi_sheet("KPI average daily sales", "avg_daily_sales", "$#,##0", "Average daily sales"),
        kpi_sheet("KPI promotion lift", "promotion_lift_pct", "0.0\"%\"",
                  "Sales lift on promotion days"),
        kpi_sheet("KPI best model MAPE", "best_model_mape_pct", "0.0\"%\"",
                  "Best model MAPE (random forest)"),
        holdout_sheet(),
        column_chart("Sales by day of week", "dow", "day", "avg_daily_sales", "day_num",
                     "Average daily sales by day of week"),
        column_chart("Sales by month", "month", "month", "avg_daily_sales", "month_num",
                     "Average daily sales by month"),
        bar_chart("Top product families", "family", "family", "sales",
                  "Product families by total sales"),
        store_sheet(),
    ]
    dash_name = "Retail sales forecasting dashboard"
    cards = ("      <cards>\n        <edge name='left'>\n          <strip size='160'>\n"
             "            <card type='pages' />\n            <card type='filters' />\n"
             "            <card type='marks' />\n          </strip>\n        </edge>\n"
             "        <edge name='top'>\n          <strip size='2147483647'>\n"
             "            <card type='columns' />\n          </strip>\n"
             "          <strip size='2147483647'>\n            <card type='rows' />\n"
             "          </strip>\n          <strip size='30'>\n            <card type='title' />\n"
             "          </strip>\n        </edge>\n      </cards>\n")
    sheet_names = [s.split("name=", 1)[1].split(">", 1)[0].strip("'\"") for s in sheets]
    viewpoints = "\n".join(f"        <viewpoint name={q(n)} />" for n in sheet_names)
    windows = (f"    <window class='dashboard' maximized='true' name={q(dash_name)}>\n"
               f"      <viewpoints>\n{viewpoints}\n      </viewpoints>\n      <active id='12' />\n      {simple_id('window-dashboard')}\n    </window>\n")
    windows += "\n".join(f"    <window class='worksheet' name={q(n)}>\n{cards}      {simple_id('window-' + n)}\n    </window>"
                         for n in sheet_names)
    return f"""<?xml version='1.0' encoding='utf-8' ?>

<workbook original-version='26.1' source-build='0.0.0 (0000.0.0.0)' source-platform='win' version='26.1' xmlns:user='http://www.tableausoftware.com/xml/user'>
  <document-format-change-manifest>
    <ManifestByVersion />
  </document-format-change-manifest>
  <preferences>
    <preference name='ui.encoding.shelf.height' value='24' />
    <preference name='ui.shelf.height' value='26' />
  </preferences>
  <datasources>
{chr(10).join(datasource(k) for k in SOURCES)}
  </datasources>
  <worksheets>
{chr(10).join(sheets)}
  </worksheets>
  <dashboards>
{dashboard()}
  </dashboards>
  <windows>
{windows}
  </windows>
  <explain-data enabled-for-viewer='true' extreme-values-enabled-for-all='true'>
    <explanation-types />
  </explain-data>
</workbook>
"""


def validate(twb_text, xsd_path):
    from lxml import etree
    schema = etree.XMLSchema(etree.parse(str(xsd_path)))
    doc = etree.fromstring(twb_text.encode("utf-8"))
    if schema.validate(doc):
        print("XSD validation: OK")
        return True
    print("XSD validation FAILED:")
    for e in schema.error_log:
        print(f"  line {e.line}: {e.message[:300]}")
    return False


def main():
    twb = build_twb()
    if len(sys.argv) > 1 and not validate(twb, sys.argv[1]):
        sys.exit(1)
    out = HERE / f"{TWB_NAME}.twbx"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{TWB_NAME}.twb", twb)
        for filename, _, _ in SOURCES.values():
            z.write(HERE / filename, f"Data/{filename}")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
