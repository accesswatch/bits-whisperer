=== BITS Registration for WooCommerce ===
Contributors: bits-org
Tags: licence, registration, woocommerce, bits-whisperer
Requires at least: 6.0
Tested up to: 6.7
Requires PHP: 8.1
Stable tag: 1.0.0
License: MIT
License URI: https://opensource.org/licenses/MIT

Automatically issues BITS Whisperer licence keys after WooCommerce
payment. Provides a "My Licence Keys" page in My Account.

== Description ==

**BITS Registration for WooCommerce** integrates the BITS Whisperer
registration system with your WooCommerce store. When a customer
purchases a BITS Whisperer licence product, the plugin automatically
triggers key issuance via GitHub Actions and displays the key on the
order confirmation page, in the confirmation email, and on a dedicated
"Licence Keys" page in the customer's My Account area.

= Features =

* Automatic key issuance on order completion
* Maps WooCommerce products to key types (annual, lifetime,
  contributor, tester)
* "My Licence Keys" page in WooCommerce My Account
* Licence key included in order confirmation emails
* Admin "Licence" column on the orders list
* Settings page for GitHub token and product mapping
* Duplicate-issuance prevention

= Requirements =

* WordPress 6.0+
* WooCommerce 8.0+
* PHP 8.1+
* A configured BITS Whisperer registry repository on GitHub

== Installation ==

1. Upload the `bits-registration` folder to `/wp-content/plugins/`.
2. Activate the plugin via **Plugins → Installed Plugins**.
3. Go to **Settings → BITS Registration**.
4. Enter your GitHub Personal Access Token (fine-grained PAT with
   **Actions: write** permission on the registry repo).
5. Configure the product-to-key-type mapping (one per line):
   `WC_PRODUCT_ID=key_type`
   Example: `42=annual`, `43=lifetime`.
6. Create WooCommerce products for each licence type you sell.

== Frequently Asked Questions ==

= Where are the keys stored? =

Keys are stored in three places:
1. **GitHub registry repo** (source of truth) — `tokens.json`
2. **WordPress database** — `wp_bits_licence_keys` table (for display)
3. **Customer's device** — via BITS Whisperer's OS credential store

= How does key issuance work? =

The plugin triggers a GitHub Actions `workflow_dispatch` event on
your private registry repository. The workflow runs the admin CLI
to generate an Ed25519-signed key and updates the public manifest.

= Can customers retrieve lost keys? =

Yes — customers can view all their keys on the **My Account →
Licence Keys** page. Keys are also included in order confirmation
emails.

== Screenshots ==

1. Settings page with GitHub token and product mapping
2. "My Licence Keys" page in customer's My Account
3. Licence key in order confirmation email

== Changelog ==

= 1.0.0 =
* Initial release
* WooCommerce integration with automatic key issuance
* My Account "Licence Keys" page
* Email integration for order confirmations
* Admin orders list "Licence" column
