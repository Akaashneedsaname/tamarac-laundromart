"""Static site generator for the laundromat website.

Usage:  python build.py
Reads site.json, writes the finished site to ./public, and lists any
business details that are still empty.
"""
import hashlib
import html
import json
import re
import shutil
import zipfile
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path(__file__).parent
OUT = ROOT / "public"
CFG = json.loads((ROOT / "site.json").read_text(encoding="utf-8"))

B = CFG["business"]
POL = CFG["policies"]
INT = CFG["integrations"]
LOC = CFG["location"]
# Delivery service areas: switched on with "service_areas_enabled" in site.json
AREAS_ON = bool(CFG.get("service_areas_enabled"))
# Customer reviews: switched on with "show_testimonials" in site.json
SHOW_REVIEWS = bool(CFG.get("show_testimonials"))
AREAS = CFG.get("service_areas", []) if AREAS_ON else []


def all_zips():
    """Every ZIP the ZIP checker accepts, mapped to the area name (or "")."""
    zmap = {str(z).strip(): B["city"] for z in CFG.get("service_zips", []) if str(z).strip()}
    for a in AREAS:
        for z in a.get("zips", []):
            if str(z).strip():
                zmap[str(z).strip()] = a.get("name", "")
    return zmap
POSTS = sorted(CFG["blog_posts"], key=lambda p: p["date"], reverse=True)

MISSING = []  # (label) of every empty field that was rendered


def asset_version(rel):
    """Short content hash, added as ?v= so browsers reload a file whenever it changes."""
    return hashlib.md5((ROOT / rel).read_bytes()).hexdigest()[:10]


CSS_V = asset_version("assets/css/styles.css")
JS_V = asset_version("assets/js/main.js")


# --------------------------------------------------------------------------
# Placeholder helpers
# --------------------------------------------------------------------------
def esc(s):
    return html.escape(str(s), quote=True)


def need(value, label):
    """Return escaped value, or a visible [placeholder] span if empty."""
    if value not in ("", None):
        return esc(value)
    if label not in MISSING:
        MISSING.append(label)
    return f'<span class="ph">[{esc(label)}]</span>'


def plain(value, label):
    """Same as need() but plain text, for <title>, meta tags and attributes."""
    if value not in ("", None):
        return str(value)
    if label not in MISSING:
        MISSING.append(label)
    return f"[{label}]"


NAME = lambda: need(B["name"], "Business Name")
NAME_T = lambda: plain(B["name"], "Business Name")
CITY = lambda: need(B["city"], "City")
CITY_T = lambda: plain(B["city"], "City")
REGION = lambda: need(B["region_name"], "Region Name")
# Optional: machine brand name, shown only when filled in
BRAND_SP = lambda: f"<strong>{esc(B['machine_brand'])}</strong> " if B.get("machine_brand") else ""
LOC_NAME = lambda: need(LOC["name"] or B["name"], "Location Name")
LOC_NAME_T = lambda: plain(LOC["name"] or B["name"], "Location Name")


def area_name(a, i):
    return need(a["name"], f"Service Area {i + 1} Name")


def area_name_t(a, i):
    return plain(a["name"], f"Service Area {i + 1} Name")


def pol(key, label):
    return need(POL.get(key, ""), label)


def full_address():
    parts = [B["street"], B["city"], B["state"], B["zip"]]
    return ", ".join(p for p in parts if p)


def address_html():
    line2 = ""
    if B["city"] or B["state"] or B["zip"]:
        line2 = esc(f'{B["city"]}, {B["state"]} {B["zip"]}'.strip(", "))
    else:
        line2 = need("", "City, State ZIP")
    return f'{need(B["street"], "Street Address")}<br>{line2}'


def tel_href():
    digits = re.sub(r"[^\d+]", "", B["phone"])
    return f"tel:{digits}" if digits else "#"


def directions_url():
    if B["latitude"] and B["longitude"]:
        dest = f'{B["latitude"]},{B["longitude"]}'
    else:
        dest = full_address()
    return f"https://www.google.com/maps/dir/?api=1&destination={quote_plus(dest)}" if dest else "#"


def map_embed(query, title):
    if not query:
        MISSING.append("Map address") if "Map address" not in MISSING else None
        return ('<div class="map-placeholder" role="img" aria-label="Map placeholder">'
                '<span>Map appears here once the address is filled in.</span></div>')
    return (f'<iframe class="map-frame" title="{esc(title)}" loading="lazy" '
            f'referrerpolicy="no-referrer-when-downgrade" '
            f'src="https://www.google.com/maps?q={quote_plus(query)}&amp;output=embed"></iframe>')


def location_query():
    if B["latitude"] and B["longitude"]:
        return f'{B["latitude"]},{B["longitude"]}'
    return full_address()


def ext(key):
    """External ordering link, '#' when not set."""
    return esc(INT.get(key) or "#")


def hours_span(h, i=0):
    """'7am - 11pm', or the open text alone (e.g. 'Open 24 hours') when there is no close time."""
    if h["open"] and h["close"]:
        return f'{esc(h["open"])} &ndash; {esc(h["close"])}'
    if h["open"]:
        return esc(h["open"])
    return need("", f"Hours Row {i + 1} Open/Close")


def hours_rows():
    rows = []
    for i, h in enumerate(B["hours"]):
        days = need(h["days"], f"Hours Row {i + 1} Days")
        span = hours_span(h, i)
        last = f' <small>(Last wash: {esc(h["last_wash"])})</small>' if h["last_wash"] else ""
        rows.append(f"<li><strong>{days}:</strong> {span}{last}</li>")
    return "".join(rows)


def img(name, alt, cls="", eager=False):
    load = "eager" if eager else "lazy"
    return f'<img src="/assets/img/{esc(name)}" alt="{esc(alt)}" class="{cls}" loading="{load}" decoding="async">'


# --------------------------------------------------------------------------
# Navigation
# --------------------------------------------------------------------------
def nav_tree():
    return [
        ("Self Service Laundry", "/self-service-laundry/", []),
        ("Wash &amp; Fold", "/wash-and-fold/", []),
        ("Pickup &amp; Delivery", "/pickup-and-delivery/", []),
        ("Commercial Laundry", "/commercial-laundry/", []),
    ] + ([
        ("Service Areas", "/service-areas/",
         [(area_name(a, i), f'/service-areas/{a["slug"]}/') for i, a in enumerate(AREAS)]),
    ] if AREAS_ON else []) + [
        ("Blog", "/blog/", []),
        ("About Us", "/about-us/", [
                                     ("Frequently Asked Questions", "/about-us/faq/"),
                                     *([("Testimonials", "/about-us/testimonials/")] if SHOW_REVIEWS else []),
                                     ("Contact Us", "/about-us/contact-us/")]),
    ]


def logo_html():
    if B["logo"]:
        return f'<img src="/assets/img/{esc(B["logo"])}" alt="{esc(B["name"])}" class="logo-img">'
    return (f'<span class="logo-mark" aria-hidden="true">'
            f'<svg viewBox="0 0 32 32"><rect x="3" y="3" width="26" height="26" rx="7" fill="currentColor"/>'
            f'<circle class="lm-ring" cx="16" cy="17.5" r="7" fill="none" stroke="#fff" stroke-width="2.4"/>'
            f'<circle class="lm-dot" cx="9" cy="8.5" r="1.4" fill="#fff"/><circle class="lm-dot" cx="13" cy="8.5" r="1.4" fill="#fff"/></svg></span>'
            f'<span class="logo-text">{NAME()}</span>')


def header(path):
    desk = []
    mobile_main = []
    mobile_subs = []
    for i, (label, href, kids) in enumerate(nav_tree()):
        active = ' aria-current="page"' if path == href else ""
        in_section = " is-active" if path.startswith(href) and href != "/" else ""
        if kids:
            sub = "".join(f'<li><a href="{h}">{l}</a></li>' for l, h in kids)
            desk.append(
                f'<li class="nav-item has-sub{in_section}"><a href="{href}"{active}>{label}</a>'
                f'<button class="sub-toggle" aria-expanded="false" aria-label="Show {label} menu">'
                f'<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M2 4l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.8"/></svg></button>'
                f'<ul class="sub-menu">{sub}</ul></li>')
            mobile_main.append(
                f'<li><button class="m-forward" data-panel="m-panel-{i}">{label}'
                f'<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M4 2l4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.8"/></svg></button></li>')
            mobile_subs.append(
                f'<div class="m-panel" id="m-panel-{i}" hidden>'
                f'<button class="m-back"><svg viewBox="0 0 12 12" aria-hidden="true"><path d="M8 2L4 6l4 4" fill="none" stroke="currentColor" stroke-width="1.8"/></svg> Back</button>'
                f'<p class="m-panel-title">{label}</p><ul>'
                f'<li><a href="{href}">{label} Main Page</a></li>{sub}</ul></div>')
        else:
            desk.append(f'<li class="nav-item{in_section}"><a href="{href}"{active}>{label}</a></li>')
            mobile_main.append(f'<li><a href="{href}">{label}</a></li>')

    hours_short = "".join(
        f'<span>{esc(h["days"]) or "[Days]"}: {hours_span(h, i)}</span>'
        for i, h in enumerate(B["hours"]))

    return f'''
<a class="skip-link" href="#main">Skip to content</a>
<div class="utility-bar">
  <div class="container utility-inner">
    <p class="utility-note">{REGION()} laundry, done right.</p>
    <ul class="utility-links">
      <li><a class="utility-cta" href="{ext("pickup_url")}">Need a Delivery or Pickup?</a></li>
    </ul>
  </div>
</div>
<header class="site-header">
  <div class="container header-inner">
    <a class="logo" href="/" aria-label="{esc(NAME_T())} home">{logo_html()}</a>
    <div class="header-info">
      <a class="info-chip" href="{esc(directions_url())}" target="_blank" rel="noopener">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2a7 7 0 0 0-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 0 0-7-7zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5z" fill="currentColor"/></svg>
        <span>{need(B["street"], "Street Address")}<small>Get directions</small></span></a>
      <div class="info-chip hours-chip">
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 7v5l3 2" fill="none" stroke="currentColor" stroke-width="2"/></svg>
        <span class="hours-lines">{hours_short}</span></div>
      <a class="info-chip phone-chip" href="{tel_href()}">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.6 10.8a15.1 15.1 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.25 11.4 11.4 0 0 0 3.6.57 1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.25.2 2.45.57 3.57a1 1 0 0 1-.25 1z" fill="currentColor"/></svg>
        <span>{need(B["phone"], "Phone")}</span></a>
      <a class="btn btn-accent header-cta" href="{ext("pickup_url")}">Need a Delivery or Pickup?</a>
    </div>
    <div class="header-mobile-actions">
      <a class="icon-btn" href="{tel_href()}" aria-label="Call us">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.6 10.8a15.1 15.1 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.25 11.4 11.4 0 0 0 3.6.57 1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.25.2 2.45.57 3.57a1 1 0 0 1-.25 1z" fill="currentColor"/></svg></a>
      <button class="icon-btn menu-toggle" aria-expanded="false" aria-controls="mobile-nav" aria-label="Open menu">
        <span class="burger" aria-hidden="true"><i></i><i></i><i></i></span></button>
    </div>
  </div>
  <nav class="main-nav" aria-label="Main">
    <div class="container"><ul class="nav-list">{"".join(desk)}</ul></div>
  </nav>
  <div class="mobile-nav" id="mobile-nav" hidden>
    <div class="m-panel is-root" id="m-panel-root">
      <ul>{"".join(mobile_main)}</ul>
      <div class="m-contact">
        <a class="btn btn-accent btn-block" href="{ext("pickup_url")}">Need a Delivery or Pickup?</a>
        <a class="btn btn-outline btn-block" href="{tel_href()}">Call {need(B["phone"], "Phone")}</a>
        <a class="btn btn-outline btn-block" href="{esc(directions_url())}" target="_blank" rel="noopener">Get Directions</a>
        <ul class="m-hours">{hours_rows()}</ul>
      </div>
    </div>
    {"".join(mobile_subs)}
  </div>
</header>'''


def social_links():
    out = []
    s = B["social"]
    if s.get("facebook"):
        out.append(f'<a href="{esc(s["facebook"])}" target="_blank" rel="noopener" aria-label="Facebook">'
                   '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 8h3V4h-3a4 4 0 0 0-4 4v2H8v4h2v8h4v-8h3l1-4h-4V8z" fill="currentColor"/></svg></a>')
    if s.get("instagram"):
        out.append(f'<a href="{esc(s["instagram"])}" target="_blank" rel="noopener" aria-label="Instagram">'
                   '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="5" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="17.5" cy="6.5" r="1.3" fill="currentColor"/></svg></a>')
    if s.get("google_reviews"):
        out.append(f'<a href="{esc(s["google_reviews"])}" target="_blank" rel="noopener" aria-label="Google reviews">'
                   '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12.2c0-.7-.1-1.3-.2-1.9H12v3.6h5a4.3 4.3 0 0 1-1.9 2.8v2.3h3A9 9 0 0 0 21 12.2zM12 21a8.9 8.9 0 0 0 6.1-2.2l-3-2.3a5.5 5.5 0 0 1-8.2-2.9H3.8v2.4A9 9 0 0 0 12 21zM6.9 13.6a5.4 5.4 0 0 1 0-3.5V7.7H3.8a9 9 0 0 0 0 8.1zM12 6.6a4.9 4.9 0 0 1 3.4 1.3l2.6-2.6A8.7 8.7 0 0 0 12 3a9 9 0 0 0-8.2 4.9l3.1 2.4A5.4 5.4 0 0 1 12 6.6z" fill="currentColor"/></svg></a>')
    return "".join(out)


def contact_block():
    """Pre-footer location/contact band shown on most pages."""
    return f'''
<section class="contact-band" aria-labelledby="contact-band-title">
  <div class="container contact-band-grid">
    <div class="contact-band-info">
      <h2 id="contact-band-title">{LOC_NAME()}</h2>
      <ul class="contact-list">
        <li><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2a7 7 0 0 0-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 0 0-7-7zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5z" fill="currentColor"/></svg>
          <span>{address_html()}</span></li>
        <li><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.6 10.8a15.1 15.1 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.25 11.4 11.4 0 0 0 3.6.57 1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.25.2 2.45.57 3.57a1 1 0 0 1-.25 1z" fill="currentColor"/></svg>
          <a href="{tel_href()}">{need(B["phone"], "Phone")}</a></li>
        <li><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 7v5l3 2" fill="none" stroke="currentColor" stroke-width="2"/></svg>
          <ul class="hours-list">{hours_rows()}</ul></li>
      </ul>
      <div class="btn-row">
        <a class="btn btn-primary" href="{esc(directions_url())}" target="_blank" rel="noopener">Get Directions</a>
        <a class="btn btn-outline" href="/about-us/contact-us/">Send a Message</a>
      </div>
    </div>
    <div class="contact-band-map">{map_embed(location_query(), "Map to " + LOC_NAME_T())}</div>
  </div>
</section>'''


def footer():
    col = lambda title, links: (f'<div class="footer-col"><h2>{title}</h2><ul>'
                                + "".join(f'<li><a href="{h}">{l}</a></li>' for l, h in links) + "</ul></div>")
    return f'''
<footer class="site-footer">
  <div class="container footer-grid">
    <div class="footer-brand">
      <a class="logo logo-light" href="/">{logo_html()}</a>
      {f"<p>{esc(B['tagline'])}</p>" if B.get("tagline") else ""}
      <div class="social">{social_links()}</div>
    </div>
    {col("Services", [("Self Service Laundry", "/self-service-laundry/"), ("Wash &amp; Fold", "/wash-and-fold/"),
                      ("Pickup &amp; Delivery", "/pickup-and-delivery/"), ("Commercial Laundry", "/commercial-laundry/")])}
    {col("Company", [("About Us", "/about-us/")] + ([("Testimonials", "/about-us/testimonials/")] if SHOW_REVIEWS else []) + [
                     ("Frequently Asked Questions", "/about-us/faq/"),
                     ("Contact Us", "/about-us/contact-us/")])}
    {col("Explore", ([("Service Areas", "/service-areas/")] if AREAS_ON else []) + [("Blog", "/blog/"),
                     ("Terms of Use", "/terms-of-use/"),
                     ("Privacy Policy", "/privacy-policy/")])}
    <div class="footer-col">
      <h2>Contact</h2>
      <p><a href="{tel_href()}">{need(B["phone"], "Phone")}</a></p>
      <p>{address_html()}<br>{esc(B["country"])}</p>
      <a class="btn btn-accent btn-sm" href="{esc(directions_url())}" target="_blank" rel="noopener">Get Directions</a>
    </div>
  </div>
  <div class="container footer-bottom">
    <p>Copyright &copy; <span data-year>{date.today().year}</span> {NAME()}. All rights reserved.</p>
  </div>
</footer>'''


# --------------------------------------------------------------------------
# Page shell
# --------------------------------------------------------------------------
def local_business_schema():
    data = {
        "@context": "https://schema.org",
        "@type": "Laundromat",
        "name": B["name"] or None,
        "telephone": B["phone"] or None,
        "email": B["email"] or None,
        "url": B["site_url"] or None,
        "logo": (B["site_url"].rstrip("/") + "/assets/img/logo-mark-512.png") if B["site_url"] else None,
        "image": (B["site_url"].rstrip("/") + "/assets/img/storefront.jpg") if B["site_url"] else None,
        "address": {
            "@type": "PostalAddress",
            "streetAddress": B["street"] or None,
            "addressLocality": B["city"] or None,
            "addressRegion": B["state"] or None,
            "postalCode": B["zip"] or None,
            "addressCountry": B["country"] or None,
        },
    }
    if B["latitude"] and B["longitude"]:
        data["geo"] = {"@type": "GeoCoordinates", "latitude": B["latitude"], "longitude": B["longitude"]}
    same = [v for v in B["social"].values() if v]
    if same:
        data["sameAs"] = same
    return data


def page(path, title, desc, body, schemas=None, contact=True, body_class=""):
    site = B["site_url"].rstrip("/")
    canonical = f"{site}{path}" if site else path
    schemas = [local_business_schema()] + (schemas or [])
    ld = "".join('<script type="application/ld+json">' + json.dumps(s, ensure_ascii=False).replace("</", "<\\/")
                 + "</script>" for s in schemas)
    gtm_head = gtm_body = ""
    if INT.get("gtm_id"):
        g = esc(INT["gtm_id"])
        gtm_head = ("<script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':new Date().getTime(),event:'gtm.js'});"
                    "var f=d.getElementsByTagName(s)[0],j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;"
                    "j.src='https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);})"
                    f"(window,document,'script','dataLayer','{g}');</script>")
        gtm_body = (f'<noscript><iframe src="https://www.googletagmanager.com/ns.html?id={g}" height="0" width="0" '
                    'style="display:none;visibility:hidden"></iframe></noscript>')
    recaptcha = ('<script src="https://www.google.com/recaptcha/api.js" async defer></script>'
                 if INT.get("recaptcha_site_key") and "data-form" in body else "")
    cfg = {
        "tawkProperty": INT.get("tawk_property_id", ""),
        "tawkWidget": INT.get("tawk_widget_id", ""),
        "formEndpoint": INT.get("form_endpoint", ""),
        "email": B["email"],
        "pickupUrl": INT.get("pickup_url", ""),
        "zips": all_zips(),
    }
    full_title = f"{title} | {NAME_T()}"
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(full_title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(canonical)}">
<meta property="og:type" content="website">
<meta property="og:title" content="{esc(full_title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:image" content="{esc(site)}/assets/img/storefront.jpg">
<meta name="theme-color" content="#0E5566">
<link rel="icon" href="/assets/img/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/assets/img/favicon-32.png" type="image/png" sizes="32x32">
<link rel="apple-touch-icon" href="/assets/img/apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500..800&amp;family=Instrument+Sans:wght@400;500;600;700&amp;display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/css/styles.css?v={CSS_V}">
{gtm_head}{ld}
<script>window.SITE={json.dumps(cfg)};</script>
<script src="/assets/js/main.js?v={JS_V}" defer></script>{recaptcha}
</head>
<body class="{body_class}">
{gtm_body}{header(path)}
<main id="main">
{body}
</main>
{contact_block() if contact else ""}
{footer()}
</body>
</html>
'''


# --------------------------------------------------------------------------
# Reusable sections
# --------------------------------------------------------------------------
def hero(title, sub, image, buttons=None):
    btns = ""
    if buttons:
        btns = '<div class="btn-row">' + "".join(
            f'<a class="btn {c}" href="{h}">{l}</a>' for l, h, c in buttons) + "</div>"
    return f'''
<section class="page-hero">
  <div class="container page-hero-grid">
    <div class="page-hero-text"><h1>{title}</h1><p class="lead">{sub}</p>{btns}</div>
    <div class="page-hero-media">{img(image, "", "cover", eager=True)}</div>
  </div>
</section>'''


def zip_form(heading="Check if we pick up in your area"):
    return f'''
<form class="zip-form" data-zip-form novalidate>
  <label for="zip-{heading[:5].lower().replace(' ', '')}" class="zip-label">{heading}</label>
  <div class="zip-row">
    <input id="zip-{heading[:5].lower().replace(' ', '')}" name="zip" inputmode="numeric" autocomplete="postal-code"
           pattern="[0-9]{{5}}" maxlength="5" placeholder="ZIP code" required>
    <button class="btn btn-accent" type="submit">Get Started</button>
  </div>
  <p class="zip-msg" role="status" aria-live="polite"></p>
</form>'''


def brand_banner():
    return f'''
<section class="brand-banner">
  <div class="container"><p>Every machine in our store is a modern, high-efficiency {BRAND_SP()}washer or dryer, built for fast, gentle cycles.</p></div>
</section>'''


def image_text(title, body, image, reverse=False, buttons=None, alt="", tone=""):
    btns = ""
    if buttons:
        btns = '<div class="btn-row">' + "".join(
            f'<a class="btn {c}" href="{h}">{l}</a>' for l, h, c in buttons) + "</div>"
    return f'''
<section class="section image-text {"is-reverse" if reverse else ""} {tone}">
  <div class="container image-text-grid">
    <div class="image-text-media">{img(image, alt, "cover")}</div>
    <div class="image-text-body"><h2>{title}</h2>{body}{btns}</div>
  </div>
</section>'''


def stars(n=5):
    n = max(0, min(5, int(n or 5)))
    return ('<span class="stars" aria-label="' + str(n) + ' out of 5 stars">'
            + "".join('<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M10 1.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L10 14.9l-5.2 2.7 1-5.8L1.5 7.7l5.9-.9z" fill="currentColor"/></svg>' for _ in range(n))
            + "</span>")


def testimonial_card(t, i):
    txt = need(t["text"], f"Testimonial {i + 1} Text")
    who = need(t["name"], f"Testimonial {i + 1} Name")
    return f'<figure class="t-card">{stars(t.get("rating", 5))}<blockquote>{txt}</blockquote><figcaption>{who}</figcaption></figure>'


def review_button():
    url = B["social"].get("google_reviews")
    return f'<a class="btn btn-outline" href="{esc(url) if url else "#"}" target="_blank" rel="noopener">Read &amp; leave reviews on Google</a>'


def testimonials_slider():
    cards = "".join(f'<div class="slide">{testimonial_card(t, i)}</div>' for i, t in enumerate(CFG["testimonials"]))
    return f'''
<section class="section testimonials">
  <div class="container">
    <div class="section-head center">
      {stars(5)}
      <h2>What our neighbors are saying</h2>
      <p>Real feedback from customers across {REGION()}.</p>
    </div>
    <div class="slider" data-slider>
      <button class="slider-btn prev" aria-label="Previous testimonial" data-prev>&#8249;</button>
      <div class="slider-track" data-track tabindex="0">{cards}</div>
      <button class="slider-btn next" aria-label="Next testimonial" data-next>&#8250;</button>
    </div>
    <div class="center">{review_button()}</div>
  </div>
</section>'''


SERVICES = [
    ("Self Service Laundry", "/self-service-laundry/", "store-3.jpg",
     "Spacious, spotless and packed with modern washers and dryers."),
    ("Wash &amp; Fold", "/wash-and-fold/", "folded.jpg",
     "Drop off your laundry and pick it up clean, fresh and neatly folded."),
    ("Pickup &amp; Delivery", "/pickup-and-delivery/", "van.jpg",
     "We collect your laundry from your door and bring it back ready to wear."),
    ("Commercial Laundry", "/commercial-laundry/", "towels.jpg",
     "Reliable, high-volume laundry service for local businesses of every size."),
]


def service_cards(title="Laundry services for every schedule"):
    cards = "".join(
        f'<a class="svc-card" href="{h}">{img(im, "", "cover")}<div class="svc-body"><h3>{t}</h3><p>{d}</p>'
        f'</div></a>'
        for t, h, im, d in SERVICES)
    return f'''
<section class="section tone-soft">
  <div class="container">
    <div class="section-head center"><h2>{title}</h2></div>
    <div class="card-grid" data-mobile-carousel>{cards}</div>
  </div>
</section>'''


def steps():
    items = [
        ("Schedule", "Book a pickup online in about a minute and pick a time window that suits you."),
        ("We clean", "We wash, dry and fold everything to your preferences, with care for every item."),
        ("We deliver", "Your fresh, folded laundry comes back to your door, ready to put away."),
    ]
    lis = "".join(f'<li class="step"><span class="step-num">{n}</span><h3>{t}</h3><p>{d}</p></li>'
                  for n, (t, d) in enumerate(items, 1))
    return f'''
<section class="section tone-brand">
  <div class="container">
    <div class="section-head center"><h2>Clean laundry in three easy steps</h2></div>
    <ol class="steps">{lis}</ol>
    <div class="center"><a class="btn btn-accent" href="{ext("pickup_url")}">Need a Delivery or Pickup?</a></div>
  </div>
</section>'''


def gallery(title, images, tone=""):
    slides = "".join(f'<figure class="slide g-slide">{img(i, a, "cover")}</figure>' for i, a in images)
    return f'''
<section class="section gallery {tone}">
  <div class="container">
    <div class="section-head center"><h2>{title}</h2></div>
    <div class="slider" data-slider>
      <button class="slider-btn prev" aria-label="Previous photo" data-prev>&#8249;</button>
      <div class="slider-track" data-track tabindex="0">{slides}</div>
      <button class="slider-btn next" aria-label="Next photo" data-next>&#8250;</button>
    </div>
  </div>
</section>'''


def area_cta():
    return f'''
<section class="section area-cta">
  <div class="container area-cta-inner">
    <div><h2>Get your weekends back.</h2><p>Enter your ZIP code to see if pickup &amp; delivery is available at your address.</p></div>
    {zip_form("Your ZIP code")}
  </div>
</section>'''


def rich(title, html_body, tone="", h="h2"):
    t = f"<{h}>{title}</{h}>" if title else ""
    return f'<section class="section {tone}"><div class="container narrow prose">{t}{html_body}</div></section>'


def action_text(kicker, title, html_body, buttons):
    btns = '<div class="btn-row">' + "".join(f'<a class="btn {c}" href="{h}">{l}</a>' for l, h, c in buttons) + "</div>"
    return f'<section class="section"><div class="container narrow prose"><h2>{title}</h2>{html_body}{btns}</div></section>'


# --------------------------------------------------------------------------
# Forms
# --------------------------------------------------------------------------
def field(name, label, kind="text", required=True, autocomplete="", full=False):
    req = " required" if required else ""
    star = ' <span aria-hidden="true">*</span>' if required else ' <span class="opt">(optional)</span>'
    ac = f' autocomplete="{autocomplete}"' if autocomplete else ""
    fid = f"f-{name}"
    cls = "field full" if full or kind == "textarea" else "field"
    if kind == "textarea":
        ctl = f'<textarea id="{fid}" name="{name}" rows="5"{req}></textarea>'
    else:
        ctl = f'<input id="{fid}" name="{name}" type="{kind}"{ac}{req}>'
    return f'<div class="{cls}"><label for="{fid}">{label}{star}</label>{ctl}<p class="field-error" aria-live="polite"></p></div>'


def form_shell(form_id, subject, fields_html, button):
    captcha = (f'<div class="field full"><div class="g-recaptcha" data-sitekey="{esc(INT["recaptcha_site_key"])}"></div></div>'
               if INT.get("recaptcha_site_key") else "")
    return f'''
<form class="site-form" data-form="{form_id}" novalidate>
  <input type="hidden" name="_subject" value="{esc(subject)}">
  <div class="hp" aria-hidden="true"><label>Leave this field empty<input type="text" name="_gotcha" tabindex="-1" autocomplete="off"></label></div>
  <div class="form-grid">{fields_html}{captcha}</div>
  <button class="btn btn-accent" type="submit">{button}</button>
  <p class="form-status" role="status" aria-live="polite"></p>
</form>'''


def contact_form():
    f = (field("first_name", "First name", autocomplete="given-name")
         + field("last_name", "Last name", autocomplete="family-name")
         + field("email", "Email", "email", autocomplete="email")
         + field("phone", "Phone", "tel", required=False, autocomplete="tel")
         + field("message", "Message", "textarea", required=False))
    return form_shell("contact", f"Website message for {NAME_T()}", f, "Send Message")


def form_section(kicker, title, form_html, aside=""):
    return f'''
<section class="section">
  <div class="container form-layout">
    <div class="form-intro"><p class="form-eyebrow">{kicker}</p><h2>{title}</h2>{aside}</div>
    <div class="form-card">{form_html}</div>
  </div>
</section>'''


# --------------------------------------------------------------------------
# FAQ content (original copy; business-specific answers use placeholders)
# --------------------------------------------------------------------------
def faq_groups():
    return [
        ("Self-Service Laundromat", [
            ("When are you open?", f"<ul class='plain'>{hours_rows()}</ul>"),
            ("How do I pay for the machines?", f"<p>We accept {pol('payment_methods', 'Payment Methods')}.</p>"),
            ("Is there an attendant on site?", f"<p>{pol('attendant_hours', 'Attendant Availability')}</p>"),
            ("Do I need to bring my own detergent?",
             "<p>You are welcome to bring your own. If you forget, detergent, softener and dryer sheets are available in store.</p>"),
            ("When is the last wash?", "<p>Last wash times are listed with our hours:</p>" + f"<ul class='plain'>{hours_rows()}</ul>"),
            ("Do you have Wi-Fi and other amenities?",
             f"<p>{pol('wifi', 'Wi-Fi Details')} {pol('amenities', 'Other Amenities')}</p>"),
            ("What kind of water do you use?", f"<p>{pol('water_type', 'Water Treatment')}</p>"),
        ]),
        ("Wash &amp; Fold (Drop-Off)", [
            ("How long does it take?", f"<p>{pol('wf_turnaround', 'Wash & Fold Turnaround')}</p>"),
            ("Is there a minimum order?", f"<p>{pol('wf_minimum', 'Wash & Fold Minimum')}</p>"),
            ("Do I need to sort my laundry first?", "<p>No. We sort every order by color and fabric before washing.</p>"),
            ("Can I leave special instructions?", "<p>Yes. Just let us know any specific instructions and we will take them into account.</p>"),
            ("Do you treat stains?", "<p>We check for visible stains and pre-treat them where it is safe for the fabric. Some stains may not come out completely.</p>"),
            ("Do you pair socks?", "<p>Yes, we match up socks as part of folding.</p>"),
            ("Can you hang clothes instead of folding them?", f"<p>{pol('hangers_policy', 'Hangers Policy')}</p>"),
            ("How is my laundry packaged?", f"<p>{pol('bagging_policy', 'Bagging / Packaging Policy')}</p>"),
        ]),
        ("Pickup &amp; Delivery", [
            ("How do I schedule a pickup?", f"<p>Check your ZIP code on our <a href='/'>home page</a>, then use the <a href='{ext('pickup_url')}'>Need a Delivery or Pickup?</a> link, or call us at <a href='{tel_href()}'>{need(B['phone'], 'Phone')}</a>.</p>"),
            ("How long until I get my laundry back?", f"<p>{pol('pd_turnaround', 'Pickup & Delivery Turnaround')}</p>"),
            ("When am I charged?", "<p>Your order is weighed after pickup and the card on file is charged once your laundry has been cleaned.</p>"),
            ("Can I make special requests?", "<p>Yes. Just let us know any specific instructions and we will take them into account.</p>"),
            ("Do I need to be home?", "<p>No. Just leave your bag in the spot you chose when booking and we will take care of the rest.</p>"),
            ("Do you treat stains and separate colors?", "<p>Yes. We sort by color and fabric and pre-treat visible stains where it is safe to do so.</p>"),
        ]),
        ("Commercial Laundry", [
            ("What kinds of businesses do you work with?", f"<p>We work with {pol('commercial_clients', 'Commercial Client Types')}</p>"),
            ("How do I get a quote?", f"<p>Call us at <a href='{tel_href()}'>{need(B['phone'], 'Phone')}</a> or <a href='/about-us/contact-us/'>send us a message</a> and we will put together a custom quote.</p>"),
            ("Do you offer custom schedules and contracts?", "<p>Yes. We build every commercial plan around your volume, schedule and budget.</p>"),
        ]),
    ]


def faq_html():
    out = []
    for gi, (group, qs) in enumerate(faq_groups()):
        items = "".join(f'<details class="acc"><summary>{q}</summary><div class="acc-body">{a}</div></details>' for q, a in qs)
        tone = "tone-soft" if gi % 2 else ""
        out.append(f'<section class="section {tone}"><div class="container narrow"><h2 class="faq-title">{group} FAQs</h2>'
                   f'<div class="acc-group">{items}</div></div></section>')
    return "".join(out)


def faq_schema():
    def strip(h):
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h)).strip()
    return {"@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": html.unescape(strip(q)),
                            "acceptedAnswer": {"@type": "Answer", "text": html.unescape(strip(a))}}
                           for _, qs in faq_groups() for q, a in qs]}


# --------------------------------------------------------------------------
# Blog helpers
# --------------------------------------------------------------------------
def fmt_date(d):
    y, m, dd = d.split("-")
    months = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
              "October", "November", "December"]
    return f"{months[int(m) - 1]} {int(dd)}, {y}"


def cat_slug(c):
    return re.sub(r"[^a-z0-9]+", "-", c.lower()).strip("-")


def blog_card(p):
    return (f'<article class="blog-card" data-cat="{cat_slug(p["category"])}">'
            f'<a href="/blog/{p["slug"]}/" class="blog-card-media">{img(p["image"], "", "cover")}</a>'
            f'<div class="blog-card-body"><p class="blog-meta"><span class="chip">{esc(p["category"])}</span>'
            f'<time datetime="{p["date"]}">{fmt_date(p["date"])}</time></p>'
            f'<h3><a href="/blog/{p["slug"]}/">{esc(p["title"])}</a></h3><p>{esc(p["excerpt"])}</p>'
            f'<a class="arrow-link" href="/blog/{p["slug"]}/">Read the article</a></div></article>')


def latest_posts():
    slides = "".join(f'<div class="slide">{blog_card(p)}</div>' for p in POSTS[:6])
    return f'''
<section class="section tone-soft">
  <div class="container">
    <div class="section-head split"><h2>From the blog</h2><a class="arrow-link" href="/blog/">See all posts</a></div>
    <div class="slider" data-slider>
      <button class="slider-btn prev" aria-label="Previous post" data-prev>&#8249;</button>
      <div class="slider-track" data-track tabindex="0">{slides}</div>
      <button class="slider-btn next" aria-label="Next post" data-next>&#8250;</button>
    </div>
  </div>
</section>'''


def breadcrumbs(items):
    lis = "".join(f'<li><a href="{h}">{l}</a></li>' if h else f'<li aria-current="page">{l}</li>' for l, h in items)
    return f'<nav class="breadcrumbs" aria-label="Breadcrumb"><ol>{lis}</ol></nav>'


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------
PAGES = {}


def add(path, *args, **kw):
    PAGES[path] = page(path, *args, **kw)


def build_pages():
    order_btn = ("Need a Delivery or Pickup?", ext("pickup_url"), "btn-accent")

    # Home ------------------------------------------------------------------
    soon = ""
    if CFG.get("coming_soon"):
        soon = (f'<p class="coming-soon"><span class="ticket-hole" aria-hidden="true"></span>'
                f'<span class="ticket-text">{esc(CFG.get("coming_soon_text") or "Coming Soon")}</span></p>')
        if CFG.get("coming_soon_subtext"):
            soon += f'<p class="coming-soon-sub">{esc(CFG["coming_soon_subtext"])}</p>'
    home = f'''
<section class="home-hero">
  <div class="container home-hero-grid">
    <div class="home-hero-text">
      {soon}
      <h1>We take laundry in {CITY()} seriously, so you can take it easy.</h1>
      <p class="lead">Use our modern self-service laundromat, drop off for wash &amp; fold, or let us pick up and deliver right to your door.</p>
      {zip_form()}
    </div>
    <div class="home-hero-media">
      <figure class="hero-photo">
        {img("storefront.jpg", "Tamarac Laundromart storefront at 4111 W Commercial Blvd", "cover", eager=True)}
      </figure>
    </div>
  </div>
</section>
{brand_banner()}
{image_text(f"A clean, bright laundromat in {CITY()}",
            f"<p>{NAME()} keeps laundry day simple. Our store is spotless, our machines are modern and well maintained, and our team is always ready to help, so you can get in, get it done and get on with your day.</p>",
            "store-2.jpg", alt="Row of washers at Tamarac Laundromart",
            buttons=[("About Us", "/about-us/", "btn-outline")])}
{testimonials_slider() if SHOW_REVIEWS else ""}
{image_text("Spend your free time on anything but laundry",
            "<p>Our wash &amp; fold and pickup &amp; delivery services take the whole chore off your plate. We sort, wash, dry and fold everything with care, then have it ready when you are.</p>",
            "folded.jpg", reverse=True, tone="tone-soft", alt="Folded laundry",
            buttons=[("Explore Wash &amp; Fold", "/wash-and-fold/", "btn-primary")])}
{image_text("Door-to-door service, on your schedule",
            "<p>Book a pickup online, leave your bag out and get it back clean and folded. It is the easiest way to keep up with laundry.</p>",
            "van.jpg", alt="Delivery van",
            buttons=[order_btn, ("How It Works", "/pickup-and-delivery/", "btn-outline")])}
{service_cards()}'''
    add("/", f"Laundromat, Wash & Fold and Pickup & Delivery in {CITY_T()}",
        f"{NAME_T()} offers self-service laundry, wash & fold and laundry pickup & delivery in {CITY_T()}.",
        home, body_class="is-home")

    # Self service ------------------------------------------------------------
    ss = (hero(f"Self-Service Laundry in {CITY()}",
               "Clean, bright and full of modern machines, so you can get in, get done and get on with your day.",
               "store-3.jpg", [("Get Directions", esc(directions_url()), "btn-primary")])
          + brand_banner()
          + gallery("Take a look inside", [("store-3.jpg", "Rows of washers at Tamarac Laundromart"), ("store-4.jpg", "Dryers and entrance area"),
                                          ("store-1.jpg", "Washers along the wall"), ("store-2.jpg", "Row of front-load washers"),
                                          ("storefront.jpg", "Tamarac Laundromart storefront")]))
    add("/self-service-laundry/", f"Self-Service Laundry in {CITY_T()}",
        f"Modern self-service laundromat in {CITY_T()} with modern washers and dryers.", ss)

    # Wash & fold ---------------------------------------------------------------
    wf = (hero(f"Wash &amp; Fold in {CITY()} and Nearby",
               "Drop off your laundry and pick it up clean, fresh and neatly folded. We handle everything in between.",
               "folded.jpg", [order_btn, ("Wash &amp; Fold FAQs", "/about-us/faq/", "btn-outline")])
          + image_text("Washed, dried and folded with care",
                       "<p>We wash, dry and neatly fold every order for you. If you have any specific instructions, just ask and we will take them into account.</p>",
                       "store-1.jpg", alt="Washers at Tamarac Laundromart", tone="tone-soft")
          + gallery("Sorted, washed and folded", [("folded.jpg", "Folded laundry"), ("store-2.jpg", "Inside Tamarac Laundromart"),
                                                  ("towels.jpg", "Folded towels"), ("store-4.jpg", "Dryers at Tamarac Laundromart")])
          # "At a glance" list: edit the wording in site.json > policies; layout is .glance in styles.css
          + f'''<section class="section glance"><div class="container">
  <h2 class="center">Wash &amp; fold at a glance</h2>
  <ul class="check-list glance-list">
    <li>Ready in {pol('wf_turnaround', 'Wash & Fold Turnaround')}</li>
    <li>{pol('wf_minimum', 'Wash & Fold Minimum')}</li>
    <li>{pol('hangers_policy', 'Hangers Policy')}</li>
    <li>{pol('bagging_policy', 'Bagging / Packaging Policy')}</li>
  </ul></div></section>'''
          + rich("", f"<p class='center big'>Drop off at {LOC_NAME()} and go enjoy your day. We will let you know when your laundry is ready.</p>", "tone-soft"))
    add("/wash-and-fold/", f"Wash & Fold Laundry Service in {CITY_T()}",
        f"Drop-off wash & fold laundry service in {CITY_T()}. Clean, fresh and folded by {NAME_T()}.", wf)

    # Pickup & delivery -----------------------------------------------------------
    pd = (hero(f"Laundry Pickup &amp; Delivery in {CITY()} and Surrounding Areas",
               "We pick up your laundry, wash and fold it, and deliver it back to your door.",
               "van.jpg", [order_btn])
          + steps()
          + image_text("Service you can count on",
                       f"<p>We pick up your laundry, wash, dry and fold it, and deliver it back to you within {pol('pd_turnaround', 'Pickup & Delivery Turnaround')}.</p>",
                       "folded.jpg", alt="Folded laundry")
          + image_text("Set it and forget it",
                       "<p>Choose weekly or every-other-week pickups and your laundry is handled automatically. Pause or skip any time.</p>",
                       "store-2.jpg", reverse=True, alt="Inside Tamarac Laundromart", tone="tone-soft")
          + gallery("Door-to-door laundry service", [("van.jpg", "Delivery van"), ("folded.jpg", "Folded laundry"),
                                                     ("towels.jpg", "Folded towels")])
          + area_cta())
    add("/pickup-and-delivery/", f"Laundry Pickup & Delivery in {CITY_T()}",
        f"Laundry pickup and delivery in {CITY_T()} and nearby areas. Schedule online with {NAME_T()}.", pd)

    # Commercial ------------------------------------------------------------------
    com = (hero(f"Commercial Laundry Service in {CITY()}",
                "Dependable, high-volume laundry for businesses that cannot afford downtime.",
                "towels.jpg", [("Call " + need(B["phone"], "Phone"), tel_href(), "btn-accent")])
           + action_text("For businesses", "Laundry service that keeps up with your business",
                         f"<p>From towels and linens to uniforms and aprons, we handle recurring commercial laundry with consistent quality and on-time pickup and delivery.</p><p>We work with {pol('commercial_clients', 'Commercial Client Types')}</p>",
                         [("Call " + need(B["phone"], "Phone"), tel_href(), "btn-accent"),
                          ("Contact Us", "/about-us/contact-us/", "btn-outline")]))
    add("/commercial-laundry/", f"Commercial Laundry Service in {CITY_T()}",
        f"Commercial laundry service for businesses in {CITY_T()} and nearby. Call for a custom quote.", com)

    # Service areas (only when enabled) -------------------------------------------------
    if AREAS_ON:
        build_service_areas(order_btn)

    # Blog -----------------------------------------------------------------------------
    cats = sorted({p["category"] for p in POSTS})
    filters = "".join(f'<label class="filter-chip"><input type="checkbox" value="{cat_slug(c)}" data-filter> {esc(c)}</label>' for c in cats)
    blog = f'''
<section class="section blog-hero">
  <div class="container">
    {breadcrumbs([("Home", "/"), ("Blog", None)])}
    <h1>The {NAME()} Blog</h1>
    <p class="lead">Laundry tips, local news and updates from our team.</p>
  </div>
</section>
<section class="section blog-listing" data-blog>
  <div class="container">
    <div class="filter-bar" role="group" aria-label="Filter posts by category"><span>Filter:</span>{filters}
      <button class="btn-link" type="button" data-clear hidden>Clear</button></div>
    <div class="blog-grid" data-results>{"".join(blog_card(p) for p in POSTS)}</div>
    <p class="no-results" data-empty hidden>No posts match those filters yet.</p>
    <div class="center"><button class="btn btn-outline" type="button" data-more hidden>Load More</button></div>
  </div>
</section>'''
    add("/blog/", "Laundry Blog", f"Laundry tips, local news and updates from {NAME_T()}.", blog)

    for p in POSTS:
        related = [q for q in POSTS if q["slug"] != p["slug"]][:3]
        body = f'''
<article class="section post">
  <div class="container narrow">
    {breadcrumbs([("Home", "/"), ("Blog", "/blog/"), (esc(p["title"]), None)])}
    <p class="blog-meta"><span class="chip">{esc(p["category"])}</span><time datetime="{p["date"]}">{fmt_date(p["date"])}</time></p>
    <h1>{esc(p["title"])}</h1>
    <div class="post-media">{img(p["image"], "", "cover", eager=True)}</div>
    <div class="prose">{p["body"]}</div>
    <div class="btn-row"><a class="btn btn-accent" href="{ext("pickup_url")}">Need a Delivery or Pickup?</a><a class="btn btn-outline" href="/blog/">Back to Blog</a></div>
  </div>
</article>
<section class="section tone-soft"><div class="container"><div class="section-head"><h2>More from the blog</h2></div>
<div class="blog-grid">{"".join(blog_card(q) for q in related)}</div></div></section>'''
        schema = {"@context": "https://schema.org", "@type": "BlogPosting", "headline": p["title"],
                  "datePublished": p["date"], "description": p["excerpt"]}
        add(f'/blog/{p["slug"]}/', p["title"], p["excerpt"], body, schemas=[schema])

    # About ----------------------------------------------------------------------------
    about = (hero(f"Modern laundry for busy {CITY()} lives", f"Get to know the team behind {NAME()}.", "store-4.jpg",
                  [("Contact Us", "/about-us/contact-us/", "btn-primary")])
             + image_text("Our story",
                          f"<p>{NAME()} is built on a simple idea: laundry should be easy, and a laundromat should be a place you actually like visiting.</p>"
                          f"<p>We keep our store clean and bright, our machines modern and well maintained, and our service friendly, so every visit is quick and stress-free for our {CITY()} neighbors.</p>"
                          "<p>Whether you wash your own clothes with us, drop them off or have them picked up, you get a team that cares about doing it right.</p>",
                          "store-3.jpg", alt="Rows of washers at Tamarac Laundromart")
             + image_text("What we care about",
                          "<ul class='check-list'><li>A spotless, well-lit, comfortable store</li><li>Machines that work, every time</li><li>Careful handling of every order</li><li>Friendly, helpful service</li></ul>",
                          "towels.jpg", reverse=True, tone="tone-soft", alt="Folded towels")
             + service_cards("How we can help")
             + latest_posts())
    add("/about-us/", "About Us", f"Learn about {NAME_T()}, a laundromat in {CITY_T()}.", about)

    contact = (hero("Contact Us", "Questions about our services or an order? We are happy to help.", "store-1.jpg")
               + form_section("Still have questions?", "Get in touch", contact_form(),
                              f"<p>Send us a message and we will reply as soon as we can, or call us at <a href='{tel_href()}'>{need(B['phone'], 'Phone')}</a>.</p>"
                              + (f"<p>Email: <a href='mailto:{esc(B['email'])}'>{esc(B['email'])}</a></p>" if B['email'] else "")))
    add("/about-us/contact-us/", "Contact Us", f"Contact {NAME_T()} in {CITY_T()}.", contact)

    faq = hero("Frequently Asked Questions", "Answers to the questions we hear most. Cannot find yours? Just ask.",
               "store-2.jpg", [("Contact Us", "/about-us/contact-us/", "btn-primary")]) + faq_html()
    add("/about-us/faq/", "Frequently Asked Questions",
        f"Answers to common questions about self-service laundry, wash & fold, pickup & delivery and commercial laundry at {NAME_T()}.",
        faq, schemas=[faq_schema()])

    if SHOW_REVIEWS:
        tgrid = "".join(testimonial_card(t, i) for i, t in enumerate(CFG["testimonials"]))
        tpage = (hero("Real reviews from real customers", "Here is what people are saying about us.", "folded.jpg")
                 + f'<section class="section"><div class="container"><div class="center">{review_button()}</div>'
                   f'<div class="t-grid">{tgrid}</div></div></section>')
        add("/about-us/testimonials/", "Testimonials", f"Customer reviews of {NAME_T()}.", tpage)

    # Legal ------------------------------------------------------------------------------
    add("/privacy-policy/", "Privacy Policy", f"Privacy policy for {NAME_T()}.", rich(f"{NAME()} Privacy Policy", privacy_text(), h="h1"))
    add("/terms-of-use/", "Terms of Use", f"Terms of use for {NAME_T()}.", rich(f"{NAME()} Terms of Use", terms_text(), h="h1"))

    # 404 ---------------------------------------------------------------------------------
    PAGES["/404.html"] = page("/404.html", "Page Not Found", "The page you are looking for could not be found.",
                              '<section class="section center"><div class="container narrow"><h1>Page not found</h1>'
                              '<p>Sorry, that page does not exist. Try the links below.</p>'
                              '<div class="btn-row center"><a class="btn btn-primary" href="/">Home</a>'
                              '<a class="btn btn-outline" href="/about-us/contact-us/">Contact Us</a></div></div></section>',
                              contact=False)


def build_service_areas(order_btn):
    zmap = all_zips()
    if not zmap and "Delivery ZIP codes" not in MISSING:
        MISSING.append("Delivery ZIP codes")
    area_cards = "".join(
        f'<a class="area-card" href="/service-areas/{a["slug"]}/"><h3>{area_name(a, i)}</h3>'
        f'<span class="area-link">Pickup &amp; delivery details</span></a>'
        for i, a in enumerate(AREAS))
    zips = ("".join(f'<span class="chip">{esc(z)}</span>' for z in sorted(zmap))
            or '<span class="ph">[Delivery ZIP codes]</span>')
    sa = f'''
<section class="section service-hero">
  <div class="container">
    <h1>Pickup &amp; delivery around {CITY()}</h1>
    <div class="service-hero-grid">
      <div class="service-map">{map_embed(", ".join(p for p in [B["city"], B["state"]] if p), "Service area map")}</div>
      <aside class="service-side">
        <h2>Is your address in our area?</h2>
        {zip_form("Enter your ZIP code")}
        <h3>ZIP codes we serve</h3>
        <div class="chip-row">{zips}</div>
      </aside>
    </div>
  </div>
</section>
<section class="section tone-brand center">
  <div class="container narrow"><h2>Less time on laundry, more time for everything else.</h2>
  <p>Book once and we will handle the washing, drying and folding.</p>
  <a class="btn btn-accent" href="{ext("pickup_url")}">Need a Delivery or Pickup?</a></div>
</section>
{f'<section class="section"><div class="container"><div class="section-head center"><h2>Areas we serve</h2></div><div class="area-grid">{area_cards}</div></div></section>' if AREAS else ""}'''
    add("/service-areas/", "Laundry Pickup & Delivery Service Areas",
        f"Check the areas and ZIP codes where {NAME_T()} offers laundry pickup and delivery.", sa)

    for i, a in enumerate(AREAS):
        nm, nm_t = area_name(a, i), area_name_t(a, i)
        intro = need(a.get("intro", ""), f"Service Area {i + 1} Intro")
        area_zips = ", ".join(esc(z) for z in a.get("zips", []))
        zip_line = f"<p><strong>ZIP codes:</strong> {area_zips}</p>" if area_zips else ""
        attractions = ""
        if a.get("attractions"):
            attractions = "<h3>Local favorites</h3><ul class='check-list'>" + "".join(
                f'<li><a href="{esc(x["url"])}" target="_blank" rel="noopener">{esc(x["name"])}</a></li>'
                for x in a["attractions"]) + "</ul>"
        body = (hero(f"Laundry Pickup &amp; Delivery in {nm}", f"Fresh, folded laundry delivered to homes and businesses in {nm}.",
                     "van.jpg", [order_btn, ("All Service Areas", "/service-areas/", "btn-outline")])
                + f'''<section class="section"><div class="container area-detail">
  <div class="prose"><h2>Pickup and delivery in {nm} and nearby</h2><p>{intro}</p>{zip_line}
  <p>Schedule a pickup online, leave your bag out, and we will bring it back clean and folded. We also offer <a href="/wash-and-fold/">wash &amp; fold</a> at our store and <a href="/commercial-laundry/">commercial laundry</a> for local businesses.</p>{attractions}</div>
  <div class="area-map">{map_embed(", ".join(p for p in [a["name"], B["state"]] if p), "Map of " + nm_t)}</div>
</div></section>'''
                + steps())
        add(f'/service-areas/{a["slug"]}/', f"Laundry Pickup & Delivery in {nm_t}",
            f"Laundry pickup and delivery service in {nm_t} from {NAME_T()}.", body)


def privacy_text():
    today = date.today().strftime("%B %d, %Y")
    return f'''
<p class="notice"><strong>Template notice:</strong> this is a starting-point policy. Have it reviewed by a legal professional before launch.</p>
<p><em>Last updated: {today}</em></p>
<p>This policy explains how {NAME()} (&ldquo;we&rdquo;, &ldquo;us&rdquo;) collects, uses and protects information when you visit this website or use our services.</p>
<h2>Information we collect</h2>
<ul><li><strong>Information you give us</strong>, such as your name, email, phone number, address and message when you fill out a form or contact us.</li>
<li><strong>Order information</strong> for pickup &amp; delivery or wash &amp; fold, handled through our online ordering provider.</li>
<li><strong>Usage information</strong>, such as pages visited and device type, collected through cookies and analytics tools.</li></ul>
<h2>How we use it</h2>
<ul><li>To respond to your questions and provide our services</li><li>To schedule, process and deliver orders</li><li>To improve our website and services</li><li>To send updates or offers, only where you have agreed to receive them</li></ul>
<h2>Sharing</h2>
<p>We do not sell your personal information. We share it only with service providers that help us run our business (for example payment, ordering, form-handling, chat and analytics providers), or when required by law.</p>
<h2>Cookies</h2>
<p>This site may use cookies for analytics and live chat. You can block or delete cookies in your browser settings.</p>
<h2>Your choices</h2>
<p>You can ask us to access, correct or delete your personal information by contacting us using the details below.</p>
<h2>Children</h2>
<p>This website is not directed at children under 13, and we do not knowingly collect their information.</p>
<h2>Contact</h2>
<p>{NAME()}<br>{address_html()}<br>Phone: {need(B["phone"], "Phone")}{"<br>Email: " + esc(B["email"]) if B["email"] else ""}</p>'''


def terms_text():
    today = date.today().strftime("%B %d, %Y")
    return f'''
<p class="notice"><strong>Template notice:</strong> these are starting-point terms. Have them reviewed by a legal professional before launch.</p>
<p><em>Last updated: {today}</em></p>
<p>By using this website you agree to these terms. If you do not agree, please do not use the site.</p>
<h2>Use of the site</h2>
<p>You may use this site for personal, non-commercial purposes. You agree not to misuse it, interfere with its operation or attempt to access it in unauthorized ways.</p>
<h2>Services</h2>
<p>Service descriptions, hours and service areas may change without notice. Orders placed through our online ordering system are also subject to that system&rsquo;s terms.</p>
<h2>Customer items</h2>
<p>We take care with every item, but we are not responsible for items left in pockets, or for damage caused by manufacturer defects, missing or incorrect care labels, or normal wear. Please tell us about any concern within a reasonable time after your order is returned.</p>
<h2>Third-party links</h2>
<p>This site links to third-party websites and services. We are not responsible for their content or practices.</p>
<h2>Content</h2>
<p>All content on this site belongs to {NAME()} or its licensors and may not be copied without permission.</p>
<h2>Disclaimer and limitation of liability</h2>
<p>This site is provided &ldquo;as is&rdquo;. To the fullest extent permitted by law, {NAME()} is not liable for indirect or consequential damages arising from your use of the site.</p>
<h2>Changes</h2>
<p>We may update these terms from time to time. Continued use of the site means you accept the updated terms.</p>
<h2>Contact</h2>
<p>{NAME()}<br>{address_html()}<br>Phone: {need(B["phone"], "Phone")}</p>'''


# --------------------------------------------------------------------------
# Write output
# --------------------------------------------------------------------------
def write():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    shutil.copytree(ROOT / "assets", OUT / "assets")
    for path, doc in PAGES.items():
        target = OUT / path.lstrip("/") if path.endswith(".html") else OUT / path.lstrip("/") / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(doc, encoding="utf-8")

    site = B["site_url"].rstrip("/")
    urls = "".join(f"<url><loc>{esc(site + p)}</loc></url>" for p in PAGES if not p.endswith(".html"))
    (OUT / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>',
        encoding="utf-8")
    robots = "User-agent: *\nAllow: /\n" + (f"Sitemap: {site}/sitemap.xml\n" if site else "")
    (OUT / "robots.txt").write_text(robots, encoding="utf-8")
    (OUT / ".htaccess").write_text(HTACCESS, encoding="utf-8")
    (OUT / "web.config").write_text(WEB_CONFIG, encoding="utf-8")
    # GitHub Pages: CNAME = custom domain, .nojekyll = serve files as-is
    host = re.sub(r"^https?://", "", B["site_url"]).strip("/")
    if host:
        (OUT / "CNAME").write_text(host + "\n", encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")

    # Ready-to-upload zip for GoDaddy (or any host): unzip into public_html
    zip_path = ROOT / "upload-to-godaddy.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(OUT.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(OUT).as_posix())


# Apache config (GoDaddy Linux / cPanel hosting)
HTACCESS = """# Generated by build.py
DirectoryIndex index.html
ErrorDocument 404 /404.html
Options -Indexes

<IfModule mod_rewrite.c>
  RewriteEngine On
  # Always use HTTPS
  RewriteCond %{HTTPS} off
  RewriteCond %{HTTP:X-Forwarded-Proto} !https
  RewriteRule ^ https://%{HTTP_HOST}%{REQUEST_URI} [L,R=301]
  # Send www to the bare domain (delete these 2 lines to keep www)
  RewriteCond %{HTTP_HOST} ^www\\.(.+)$ [NC]
  RewriteRule ^ https://%1%{REQUEST_URI} [L,R=301]
</IfModule>

<IfModule mod_deflate.c>
  AddOutputFilterByType DEFLATE text/html text/css application/javascript image/svg+xml application/xml text/plain
</IfModule>

<IfModule mod_expires.c>
  ExpiresActive On
  ExpiresByType text/html "access plus 0 seconds"
  ExpiresByType text/css "access plus 7 days"
  ExpiresByType application/javascript "access plus 7 days"
  ExpiresByType image/jpeg "access plus 30 days"
  ExpiresByType image/svg+xml "access plus 30 days"
</IfModule>
"""

# IIS config (GoDaddy Windows / Plesk hosting). Ignored by Linux hosting.
WEB_CONFIG = """<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <system.webServer>
    <defaultDocument><files><clear /><add value="index.html" /></files></defaultDocument>
    <httpErrors errorMode="Custom" existingResponse="Replace">
      <remove statusCode="404" />
      <error statusCode="404" path="/404.html" responseMode="ExecuteURL" />
    </httpErrors>
    <staticContent>
      <remove fileExtension=".svg" />
      <mimeMap fileExtension=".svg" mimeType="image/svg+xml" />
    </staticContent>
  </system.webServer>
</configuration>
"""


def main():
    build_pages()
    write()
    print(f"Built {len(PAGES)} pages into {OUT}")
    print(f"Upload file ready: {ROOT / 'upload-to-godaddy.zip'}")
    if not B["site_url"]:
        MISSING.append("Website URL (business.site_url) - needed for canonical links and sitemap")
    if MISSING:
        print(f"\n{len(MISSING)} details still to fill in (shown as [placeholders] on the site):")
        for m in MISSING:
            print("  -", m)
    unset = [k for k, v in INT.items() if not k.startswith("_") and not v]
    if unset:
        print("\nIntegrations not configured (links point to '#', features disabled):")
        for k in unset:
            print("  -", k)


if __name__ == "__main__":
    sys.exit(main())
