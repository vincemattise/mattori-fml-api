"""
Mattori email HTML templates.
Called by server.py to build email HTML from template type + data.
"""

from urllib.parse import quote

# Shared building blocks
_HEAD = """<!DOCTYPE html>
<html lang="nl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title}</title>
<style>@media only screen and (max-width:600px){{.email-body,.email-wrapper,.email-wrapper-td{{background-color:#f0f0ec !important;}}.email-wrapper-td{{padding:20px 0 !important;}}.email-container{{border-radius:0 !important;}}}}</style>
</head><body class="email-body" style="margin:0;padding:0;background:#fafaf8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<table class="email-wrapper" role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#fafaf8;"><tr>
<td class="email-wrapper-td" align="center" style="padding:40px 20px;">
<table class="email-container" role="presentation" width="520" cellpadding="0" cellspacing="0" style="max-width:100%;background:#f0f0ec;border-radius:14px;overflow:hidden;table-layout:fixed;">"""

_LOGO = """<tr><td style="padding:40px 40px 0 40px;text-align:center;">
<img src="https://cdn.shopify.com/s/files/1/0958/8614/7958/files/TT_dik.png?v=1770208484" alt="Mattori" width="48" style="display:block;width:48px;height:auto;margin:0 auto 32px auto;">"""

_DIVIDER = """<tr><td style="padding:28px 40px;"><div style="height:1px;background:#e8e8e4;"></div></td></tr>"""

_CONTACT = """<tr><td style="padding:0 40px;text-align:center;"><p style="font-size:13px;color:#aaa;margin:0;">
Vragen? Stuur een berichtje via <a href="https://wa.me/31683807190" style="color:#1a1a1a;text-decoration:underline;font-weight:600;">WhatsApp</a><br>of mail naar <a href="mailto:vince@mattori.nl" style="color:#1a1a1a;text-decoration:underline;font-weight:600;">vince@mattori.nl</a></p></td></tr>"""

_FOOTER = """<tr><td style="padding:32px 40px 40px 40px;text-align:center;"><p style="font-size:12px;color:#ccc;margin:0;">
Mattori Frame\u00B3 \u00B7 mattori.nl</p></td></tr>
</table></td></tr></table></body></html>"""

def _step(num, title, desc):
    return f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:20px;"><tr>
<td width="36" valign="top"><div style="width:28px;height:28px;background:#1a1a1a;color:#fff;border-radius:50%;font-size:13px;font-weight:700;line-height:28px;text-align:center;">{num}</div></td>
<td style="padding-left:12px;"><p style="font-size:14px;font-weight:700;color:#1a1a1a;margin:0 0 2px 0;">{title}</p>
<p style="font-size:13px;color:#777;line-height:1.5;margin:0;">{desc}</p></td></tr></table>"""

def _detail_row(label, value, last=False):
    pb = "" if last else "padding-bottom:8px;"
    return f"""<tr><td style="font-size:13px;color:#888;{pb}">{label}</td>
<td style="font-size:13px;color:#1a1a1a;font-weight:600;{pb}text-align:right;word-break:break-all;">{value}</td></tr>"""

def _detail_card(rows_html):
    return f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#fafaf8;border-radius:10px;">
<tr><td style="padding:20px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">
{rows_html}</table></td></tr></table>"""

def _numbered_item(num, title, desc):
    return f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#fafaf8;border-radius:10px;margin-bottom:10px;">
<tr><td style="padding:16px 20px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
<td width="28" valign="top"><div style="width:24px;height:24px;background:#1a1a1a;color:#fff;border-radius:50%;font-size:12px;font-weight:700;line-height:24px;text-align:center;">{num}</div></td>
<td style="padding-left:12px;"><p style="font-size:14px;font-weight:700;color:#1a1a1a;margin:0 0 2px 0;">{title}</p>
<p style="font-size:13px;color:#777;line-height:1.5;margin:0;">{desc}</p></td></tr></table></td></tr></table>"""


def _esc(val):
    """Escape HTML special characters."""
    return str(val).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ─── TEMPLATE: sample bevestiging ───

def sample_bevestiging(d):
    naam = _esc(d.get("naam", ""))
    bedrijf = _esc(d.get("bedrijf", ""))
    email = _esc(d.get("email", ""))
    telefoon = _esc(d.get("telefoon", "-"))
    funda = _esc(d.get("funda_link", ""))
    adres = _esc(d.get("adres", ""))
    logo = _esc(d.get("logo", "-"))

    return (
        _HEAD.format(title="Je sample aanvraag is ontvangen")
        + _LOGO
        + f'<h1 style="font-size:24px;font-weight:800;color:#1a1a1a;margin:0 0 12px 0;letter-spacing:-0.8px;line-height:1.2;">Je sample aanvraag is ontvangen</h1>'
        + f'<p style="font-size:15px;color:#777;line-height:1.6;margin:0;">Goed nieuws, {naam}. We zijn begonnen met het maken van je Mattori Frame\u00B3. Zodra het wordt verzonden ontvang je een mail met track &amp; trace. Ondertussen benieuwd naar meer, zoals <a href="https://mattori.nl/pages/over-ons" style="color:#777;text-decoration:underline;">wie dit maakt</a>?</p>'
        + '</td></tr>'
        + _DIVIDER
        + '<tr><td style="padding:0 40px;">'
        + '<p style="font-size:13px;font-weight:600;color:#aaa;letter-spacing:0.5px;margin:0 0 20px 0;text-transform:uppercase;">Wat gebeurt er nu?</p>'
        + _step("1", "We maken je sample", "Op basis van jouw Funda-link maken we een uniek 3D-kunstwerk voor jou of je klant. Dit doen we met de hand, dit duurt gemiddeld 2 werkdagen.")
        + _step("2", "We versturen je sample", "Zodra je sample klaar is en wordt verzonden, ontvang je een mail met track &amp; trace.")
        + '</td></tr>'
        + _DIVIDER
        + '<tr><td style="padding:0 40px;">'
        + '<p style="font-size:13px;font-weight:600;color:#aaa;letter-spacing:0.5px;margin:0 0 16px 0;text-transform:uppercase;">Je aanvraag</p>'
        + _detail_card(
            _detail_row("Naam", naam)
            + _detail_row("Bedrijf", bedrijf)
            + _detail_row("E-mail", email)
            + _detail_row("Telefoon", telefoon)
            + _detail_row("Funda-link", funda)
            + _detail_row("Afleveradres", adres)
            + _detail_row("Logo", logo, last=True)
        )
        + '</td></tr>'
        + _DIVIDER
        + _CONTACT
        + _FOOTER
    )


# ─── TEMPLATE: contact opvolging ───

def contact_opvolging(d):
    naam = _esc(d.get("naam", ""))
    bedrijf = _esc(d.get("bedrijf", ""))

    return (
        _HEAD.format(title="Leuk dat je interesse hebt")
        + _LOGO
        + f'<h1 style="font-size:24px;font-weight:800;color:#1a1a1a;margin:0 0 12px 0;letter-spacing:-0.8px;line-height:1.2;">Leuk dat je interesse hebt, {naam}</h1>'
        + f'<p style="font-size:15px;color:#777;line-height:1.6;margin:0;">We maken graag een gratis Mattori Frame\u00B3 sample voor je. Stuur onderstaande gegevens als reactie op deze mail, dan gaan we direct aan de slag.</p>'
        + '</td></tr>'
        + _DIVIDER
        + '<tr><td style="padding:0 40px;">'
        + '<p style="font-size:13px;font-weight:600;color:#aaa;letter-spacing:0.5px;margin:0 0 20px 0;text-transform:uppercase;">Wat hebben we nodig?</p>'
        + _numbered_item("1", "Een Funda-link", "De link naar de woning waarvan je een Frame\u00B3 wilt. Ga naar funda.nl, zoek de woning op en kopieer de link uit je adresbalk.")
        + _numbered_item("2", "Je afleveradres", "Waar mogen we de sample naartoe sturen?")
        + _numbered_item("3", 'Je logo <span style="font-weight:500;color:#aaa;font-size:12px;">(optioneel)</span>', "Wil je jouw logo op het frame? Stuur het mee als bijlage of link. PNG of SVG werkt het best.")
        + '</td></tr>'
        + _DIVIDER
        + f'<tr><td style="padding:0 40px;text-align:center;"><p style="font-size:13px;color:#aaa;margin:0;">Reply op deze mail, stuur een berichtje via <a href="https://wa.me/31683807190" style="color:#1a1a1a;text-decoration:underline;font-weight:600;">WhatsApp</a><br>of mail naar <a href="mailto:vince@mattori.nl?subject=Sample%20aanvraag%20{quote(bedrijf)}" style="color:#1a1a1a;text-decoration:underline;font-weight:600;">vince@mattori.nl</a></p></td></tr>'
        + _FOOTER
    )


# ─── TEMPLATE: verzendbevestiging ───

def verzendbevestiging(d):
    naam = _esc(d.get("naam", ""))
    adres = _esc(d.get("adres", ""))
    tracking_link = d.get("tracking_link", "#")

    return (
        _HEAD.format(title="Je sample is onderweg")
        + _LOGO
        + f'<h1 style="font-size:24px;font-weight:800;color:#1a1a1a;margin:0 0 12px 0;letter-spacing:-0.8px;line-height:1.2;">Je sample is onderweg!</h1>'
        + f'<p style="font-size:15px;color:#777;line-height:1.6;margin:0;">Goed nieuws, {naam}. Je Mattori Frame\u00B3 is met de hand gemaakt en onderweg naar je. Hieronder vind je alle details over de bezorging.</p>'
        + '</td></tr>'
        + _DIVIDER
        # Track & Trace button
        + '<tr><td style="padding:0 40px;">'
        + '<p style="font-size:13px;font-weight:600;color:#aaa;letter-spacing:0.5px;margin:0 0 16px 0;text-transform:uppercase;">Track &amp; Trace</p>'
        + '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#fafaf8;border-radius:10px;">'
        + '<tr><td style="padding:24px 20px;text-align:center;">'
        + f'<a href="{tracking_link}" style="display:inline-block;background:#1a1a1a;color:#ffffff;padding:14px 28px;border-radius:10px;font-size:14px;font-weight:600;text-decoration:none;">Volg je pakket \u2192</a>'
        + '</td></tr></table></td></tr>'
        + _DIVIDER
        # Steps
        + '<tr><td style="padding:0 40px;">'
        + '<p style="font-size:13px;font-weight:600;color:#aaa;letter-spacing:0.5px;margin:0 0 20px 0;text-transform:uppercase;">Wat gebeurt er nu?</p>'
        + _step("1", "Pakket onderweg", "Je Mattori Frame\u00B3 sample is zojuist overgedragen aan PostNL. Gebruik de track &amp; trace link hierboven om de status te volgen.")
        + _step("2", "Bezorging", "Doorgaans de volgende werkdag wordt je sample bezorgd. PostNL levert het pakket bij je aan de deur of bij een afhaalpunt in de buurt.")
        + _step("3", "Bekijk en ervaar", "Pak je Frame\u00B3 sample uit en ontdek de kwaliteit. We nemen binnenkort contact met je op om te horen wat je ervan vindt.")
        + '</td></tr>'
        + _DIVIDER
        # Package contents
        + '<tr><td style="padding:0 40px;">'
        + '<p style="font-size:13px;font-weight:600;color:#aaa;letter-spacing:0.5px;margin:0 0 16px 0;text-transform:uppercase;">Wat zit er in je pakket?</p>'
        + _detail_card(
            _detail_row("Product", "Mattori Frame\u00B3 sample")
            + _detail_row("Adres", adres)
            + _detail_row("Op maat gemaakt voor", naam, last=True)
        )
        + '</td></tr>'
        + _DIVIDER
        + _CONTACT
        + _FOOTER
    )


# ─── Dispatcher ───

TEMPLATES = {
    "sample": sample_bevestiging,
    "contact": contact_opvolging,
    "verzending": verzendbevestiging,
}

SUBJECTS = {
    "sample": lambda d: "Je Mattori Frame\u00B3 sample aanvraag is ontvangen",
    "contact": lambda d: f"Fijn dat je contact opneemt, {d.get('naam', '')}",
    "verzending": lambda d: "Je Mattori Frame\u00B3 sample is onderweg!",
}
