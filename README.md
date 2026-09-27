# Laundromat Website

A static website (plain HTML/CSS/JS). It needs no database and can be hosted anywhere, e.g. Netlify, Cloudflare Pages, GitHub Pages or any web host.

## Editing details
1. Open `site.json` and fill in the empty `""` values (business name, phone, address, hours, prices, service areas, and so on).
2. Run `python build.py`.
3. The finished site is written to `public/`. Upload the contents of that folder to your host.

Any detail still empty shows on the site as a yellow **[Placeholder]**, and `build.py` lists every one of them.

## Preview locally
    cd public
    python -m http.server 8000
Then open http://localhost:8000

## Publishing on GitHub Pages (domain stays at GoDaddy)
The finished site is the **`public`** folder. A GitHub Actions workflow (`.github/workflows/pages.yml`)
publishes it automatically every time you push to the `main` branch.

**First-time setup**
1. On github.com, create a new **public** repository (e.g. `tamarac-laundromart`), with no README.
2. In this folder, run:
       git remote add origin https://github.com/<your-username>/tamarac-laundromart.git
       git push -u origin main
3. Repository > **Settings > Pages** > Build and deployment > Source: **GitHub Actions**.
4. **Actions** tab: wait for "Deploy site to GitHub Pages" to finish (green tick).
5. Settings > Pages > Custom domain: enter `tamaraclaundromart.com` and save.

**GoDaddy DNS** (Domains > tamaraclaundromart.com > DNS)
- Delete GoDaddy's parking `A` record for `@` and any domain forwarding.
- Add four `A` records for `@`: 185.199.108.153, 185.199.109.153, 185.199.110.153, 185.199.111.153
- Add (or edit) a `CNAME` record: name `www`, value `<your-username>.github.io`
- Once the DNS check passes in Settings > Pages (minutes to a few hours), tick **Enforce HTTPS**.

**To update the site later:** edit `site.json`, run `python build.py`, then
    git add -A
    git commit -m "Update site"
    git push

`public/CNAME` holds the custom domain and `public/.nojekyll` tells GitHub to serve the files as-is.
The `.htaccess` and `web.config` files are only used by other hosts and are ignored by GitHub Pages.

## Publishing on GoDaddy
`python build.py` also creates **`upload-to-godaddy.zip`**, which is the whole site ready to upload.

**You need a GoDaddy *Web Hosting* plan (cPanel)**, not just the domain. GoDaddy's "Website Builder" / "Websites + Marketing" cannot accept uploaded files.

1. In `site.json`, set `business.site_url` to your domain (e.g. `"https://yourdomain.com"`), then run `python build.py`.
2. GoDaddy > **My Products** > **Web Hosting** > **Manage** > **cPanel Admin** > **File Manager**.
3. Open the **public_html** folder. If it has a default GoDaddy page (e.g. `index.php` or `default.html`), delete it.
4. Click **Upload**, choose `upload-to-godaddy.zip`, then go back, right-click the zip > **Extract** into `public_html`, and delete the zip afterwards.
   - The files (`index.html`, `assets`, `about-us`, ...) must sit **directly** in `public_html`, not in a subfolder.
5. Turn on free SSL: cPanel > **SSL/TLS Status** > run AutoSSL (usually already on). The included `.htaccess` redirects every visitor to `https://`.
6. If the domain and hosting were bought separately, make sure the domain points to the hosting: GoDaddy > **Domains** > your domain > **DNS**. The hosting plan's setup normally does this for you.

**To update the site later:** edit `site.json`, run `python build.py`, and upload the new zip the same way (overwrite when asked).

`.htaccess` handles HTTPS, the custom 404 page, compression and caching on Linux hosting. `web.config` does the same job on Windows hosting. Leave both in place; each host ignores the one it doesn't use.

## Opening Soon badge
In `site.json`: `coming_soon` (true/false) shows or hides it, `coming_soon_text` is the badge text, and `coming_soon_subtext` is the line under it.

## Integrations (in `site.json` > `integrations`)
| Key | What it does |
|---|---|
| `order_*_url` | Links for Sign Up, Log In, Dashboard, Manage Account and Schedule Pickup (your online ordering system) |
| `form_endpoint` | Where the contact and bid forms send submissions (e.g. a Formspree form URL). If it is empty, the forms open the visitor's email app addressed to `business.email` |
| `recaptcha_site_key` | Optional Google reCAPTCHA v2 on the forms |
| `tawk_property_id` / `tawk_widget_id` | Optional tawk.to live chat |
| `gtm_id` | Optional Google Tag Manager / Analytics |

`service_zips`: the ZIP codes you deliver to. The ZIP checker only sends visitors in these ZIPs to sign up. If the list is empty, every valid ZIP is accepted.

## Styling
Colors and fonts are set at the top of `assets/css/styles.css` (`:root`). To change the logo, put the image in `assets/img/` and set `business.logo` to its filename.

## Placeholder photos
Public-domain / CC0 photos from Wikimedia Commons, in `assets/img/`. Replace them with your own photos using the same filenames.

## Legal pages
The Privacy Policy and Terms of Use are starting templates. Have them reviewed before launch.
