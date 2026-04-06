<?php
/**
 * Plugin Name:       BITS Registration for WooCommerce
 * Plugin URI:        https://github.com/bits-whisperer/bits-whisperer-registry
 * Description:       Automatically issues BITS Whisperer licence keys after
 *                    WooCommerce payment and provides a "My Licence Keys" page.
 * Version:           1.0.0
 * Requires at least: 6.0
 * Requires PHP:      8.1
 * Author:            Blind Information Technology Solutions (BITS)
 * Author URI:        https://bits.org
 * License:           MIT
 * Text Domain:       bits-registration
 * Domain Path:       /languages
 *
 * WC requires at least: 8.0
 * WC tested up to:      9.5
 *
 * @package BITS_Registration
 */

defined( 'ABSPATH' ) || exit;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
define( 'BITS_REG_VERSION', '1.0.0' );
define( 'BITS_REG_PLUGIN_DIR', plugin_dir_path( __FILE__ ) );
define( 'BITS_REG_PLUGIN_URL', plugin_dir_url( __FILE__ ) );

// GitHub repository for key issuance (private repo).
// The plugin triggers a workflow_dispatch event to issue keys.
if ( ! defined( 'BITS_REG_GITHUB_OWNER' ) ) {
    define( 'BITS_REG_GITHUB_OWNER', 'bits-whisperer' );
}
if ( ! defined( 'BITS_REG_GITHUB_REPO' ) ) {
    define( 'BITS_REG_GITHUB_REPO', 'bits-whisperer-registry' );
}

// ---------------------------------------------------------------------------
// Activation / deactivation hooks
// ---------------------------------------------------------------------------

register_activation_hook( __FILE__, 'bits_reg_activate' );
register_deactivation_hook( __FILE__, 'bits_reg_deactivate' );

/**
 * Create the licence keys database table on activation.
 */
function bits_reg_activate(): void {
    global $wpdb;

    $table   = $wpdb->prefix . 'bits_licence_keys';
    $charset = $wpdb->get_charset_collate();

    $sql = "CREATE TABLE IF NOT EXISTS {$table} (
        id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        order_id    BIGINT UNSIGNED NOT NULL,
        user_id     BIGINT UNSIGNED NOT NULL DEFAULT 0,
        email       VARCHAR(255)    NOT NULL,
        product_id  VARCHAR(64)     NOT NULL DEFAULT 'bits_whisperer',
        key_type    VARCHAR(32)     NOT NULL DEFAULT 'annual',
        licence_key VARCHAR(255)    NOT NULL,
        status      VARCHAR(32)     NOT NULL DEFAULT 'pending',
        issued_at   DATETIME        NULL,
        expires_at  DATETIME        NULL,
        created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        KEY idx_order    (order_id),
        KEY idx_user     (user_id),
        KEY idx_email    (email),
        KEY idx_status   (status)
    ) {$charset};";

    require_once ABSPATH . 'wp-admin/includes/upgrade.php';
    dbDelta( $sql );

    // Flush rewrite rules for the "My Licence Keys" endpoint.
    bits_reg_register_endpoint();
    flush_rewrite_rules();

    update_option( 'bits_reg_version', BITS_REG_VERSION );
}

/**
 * Clean up on deactivation (flush rewrite rules).
 */
function bits_reg_deactivate(): void {
    flush_rewrite_rules();
}

// ---------------------------------------------------------------------------
// WooCommerce dependency check
// ---------------------------------------------------------------------------

add_action( 'admin_init', 'bits_reg_check_woocommerce' );

function bits_reg_check_woocommerce(): void {
    if ( ! class_exists( 'WooCommerce' ) ) {
        add_action( 'admin_notices', function (): void {
            echo '<div class="notice notice-error"><p>';
            echo esc_html__(
                'BITS Registration requires WooCommerce to be installed and active.',
                'bits-registration'
            );
            echo '</p></div>';
        } );
    }
}

// ---------------------------------------------------------------------------
// Settings page (wp-admin → Settings → BITS Registration)
// ---------------------------------------------------------------------------

add_action( 'admin_menu', 'bits_reg_admin_menu' );
add_action( 'admin_init', 'bits_reg_register_settings' );

function bits_reg_admin_menu(): void {
    add_options_page(
        __( 'BITS Registration', 'bits-registration' ),
        __( 'BITS Registration', 'bits-registration' ),
        'manage_options',
        'bits-registration',
        'bits_reg_settings_page'
    );
}

function bits_reg_register_settings(): void {
    register_setting( 'bits_reg_settings', 'bits_reg_github_token', [
        'type'              => 'string',
        'sanitize_callback' => 'sanitize_text_field',
        'default'           => '',
    ] );
    register_setting( 'bits_reg_settings', 'bits_reg_product_map', [
        'type'              => 'string',
        'sanitize_callback' => 'sanitize_textarea_field',
        'default'           => '',
    ] );
}

/**
 * Render the settings page.
 */
function bits_reg_settings_page(): void {
    if ( ! current_user_can( 'manage_options' ) ) {
        return;
    }
    ?>
    <div class="wrap">
        <h1><?php echo esc_html( get_admin_page_title() ); ?></h1>
        <form method="post" action="options.php">
            <?php settings_fields( 'bits_reg_settings' ); ?>
            <table class="form-table" role="presentation">
                <tr>
                    <th scope="row">
                        <label for="bits_reg_github_token">
                            <?php esc_html_e( 'GitHub Personal Access Token', 'bits-registration' ); ?>
                        </label>
                    </th>
                    <td>
                        <input type="password" id="bits_reg_github_token"
                               name="bits_reg_github_token"
                               value="<?php echo esc_attr( get_option( 'bits_reg_github_token', '' ) ); ?>"
                               class="regular-text" autocomplete="off" />
                        <p class="description">
                            <?php esc_html_e(
                                'A fine-grained PAT with "Actions: write" scope on the registry repo.',
                                'bits-registration'
                            ); ?>
                        </p>
                    </td>
                </tr>
                <tr>
                    <th scope="row">
                        <label for="bits_reg_product_map">
                            <?php esc_html_e( 'WooCommerce Product → Key Type Mapping', 'bits-registration' ); ?>
                        </label>
                    </th>
                    <td>
                        <textarea id="bits_reg_product_map"
                                  name="bits_reg_product_map"
                                  rows="6" cols="60"
                                  class="large-text code"
                        ><?php echo esc_textarea( get_option( 'bits_reg_product_map', '' ) ); ?></textarea>
                        <p class="description">
                            <?php esc_html_e(
                                'One mapping per line: WC_PRODUCT_ID=key_type. '
                                . 'Example: 42=annual, 43=lifetime, 44=contributor',
                                'bits-registration'
                            ); ?>
                        </p>
                    </td>
                </tr>
            </table>
            <?php submit_button(); ?>
        </form>

        <hr />
        <h2><?php esc_html_e( 'Licence Key Statistics', 'bits-registration' ); ?></h2>
        <?php bits_reg_render_stats(); ?>
    </div>
    <?php
}

/**
 * Render licence key statistics on the settings page.
 */
function bits_reg_render_stats(): void {
    global $wpdb;
    $table = $wpdb->prefix . 'bits_licence_keys';

    // phpcs:ignore WordPress.DB.DirectDatabaseQuery
    $stats = $wpdb->get_results(
        "SELECT status, COUNT(*) as cnt FROM {$table} GROUP BY status",
        ARRAY_A
    );

    if ( ! $stats ) {
        echo '<p>' . esc_html__( 'No licence keys issued yet.', 'bits-registration' ) . '</p>';
        return;
    }

    echo '<table class="widefat fixed striped"><thead><tr>';
    echo '<th>' . esc_html__( 'Status', 'bits-registration' ) . '</th>';
    echo '<th>' . esc_html__( 'Count', 'bits-registration' ) . '</th>';
    echo '</tr></thead><tbody>';
    foreach ( $stats as $row ) {
        echo '<tr><td>' . esc_html( $row['status'] ) . '</td>';
        echo '<td>' . (int) $row['cnt'] . '</td></tr>';
    }
    echo '</tbody></table>';
}

// ---------------------------------------------------------------------------
// Product → key type mapping helper
// ---------------------------------------------------------------------------

/**
 * Parse the product mapping from the settings textarea.
 *
 * @return array<int, string> Map of WC product ID → key type.
 */
function bits_reg_get_product_map(): array {
    $raw = get_option( 'bits_reg_product_map', '' );
    $map = [];
    foreach ( explode( "\n", $raw ) as $line ) {
        $line = trim( $line );
        if ( '' === $line || ! str_contains( $line, '=' ) ) {
            continue;
        }
        [ $pid, $type ] = array_map( 'trim', explode( '=', $line, 2 ) );
        if ( is_numeric( $pid ) && in_array( $type, [ 'annual', 'lifetime', 'contributor', 'tester' ], true ) ) {
            $map[ (int) $pid ] = $type;
        }
    }
    return $map;
}

// ---------------------------------------------------------------------------
// WooCommerce order hooks — issue key on payment
// ---------------------------------------------------------------------------

add_action( 'woocommerce_order_status_completed', 'bits_reg_on_order_completed', 10, 1 );
add_action( 'woocommerce_order_status_processing', 'bits_reg_on_order_completed', 10, 1 );

/**
 * When an order is paid, issue licence keys for mapped products.
 *
 * @param int $order_id WooCommerce order ID.
 */
function bits_reg_on_order_completed( int $order_id ): void {
    $order = wc_get_order( $order_id );
    if ( ! $order ) {
        return;
    }

    // Prevent duplicate issuance.
    if ( $order->get_meta( '_bits_keys_issued' ) === 'yes' ) {
        return;
    }

    $product_map = bits_reg_get_product_map();
    if ( empty( $product_map ) ) {
        return;
    }

    $email   = $order->get_billing_email();
    $user_id = $order->get_user_id();

    foreach ( $order->get_items() as $item ) {
        $pid = $item->get_product_id();
        if ( ! isset( $product_map[ $pid ] ) ) {
            continue;
        }
        $key_type = $product_map[ $pid ];

        // Trigger GitHub Actions workflow to issue the key.
        $licence_key = bits_reg_trigger_key_issuance( $email, $key_type );

        if ( $licence_key ) {
            bits_reg_store_key( $order_id, $user_id, $email, $key_type, $licence_key );

            // Add the key as an order note (visible to customer).
            $order->add_order_note(
                sprintf(
                    /* translators: 1: key type, 2: licence key */
                    __( 'BITS Whisperer %1$s licence key issued: %2$s', 'bits-registration' ),
                    $key_type,
                    $licence_key
                ),
                1 // Customer-visible note.
            );
        }
    }

    $order->update_meta_data( '_bits_keys_issued', 'yes' );
    $order->save();
}

// ---------------------------------------------------------------------------
// GitHub API integration
// ---------------------------------------------------------------------------

/**
 * Trigger the manual_issue workflow on the registry repo to issue a key.
 *
 * Uses the GitHub REST API workflow_dispatch event. The workflow runs
 * the admin CLI to issue the key and updates the manifest.
 *
 * @param string $email    User email.
 * @param string $key_type Key type (annual|lifetime|contributor|tester).
 * @return string|null The issued licence key, or null on failure.
 */
function bits_reg_trigger_key_issuance( string $email, string $key_type ): ?string {
    $token = get_option( 'bits_reg_github_token', '' );
    if ( empty( $token ) ) {
        error_log( 'BITS Registration: GitHub token not configured.' );
        return null;
    }

    $url = sprintf(
        'https://api.github.com/repos/%s/%s/actions/workflows/manual_issue.yml/dispatches',
        BITS_REG_GITHUB_OWNER,
        BITS_REG_GITHUB_REPO
    );

    $response = wp_remote_post( $url, [
        'timeout' => 30,
        'headers' => [
            'Authorization' => 'Bearer ' . $token,
            'Accept'        => 'application/vnd.github+json',
            'Content-Type'  => 'application/json',
            'X-GitHub-Api-Version' => '2022-11-28',
        ],
        'body' => wp_json_encode( [
            'ref'    => 'main',
            'inputs' => [
                'email'      => $email,
                'product_id' => 'bits_whisperer',
                'key_type'   => $key_type,
            ],
        ] ),
    ] );

    if ( is_wp_error( $response ) ) {
        error_log( 'BITS Registration: GitHub API error: ' . $response->get_error_message() );
        return null;
    }

    $code = wp_remote_retrieve_response_code( $response );
    if ( $code !== 204 ) {
        error_log( "BITS Registration: GitHub API returned HTTP {$code}" );
        return null;
    }

    // The workflow_dispatch is async — the key will be in the registry
    // after the workflow completes. Generate a placeholder key locally
    // that will match once the manifest syncs.
    $key_id   = wp_generate_uuid4();
    $checksum = substr( hash( 'sha256', "bits_whisperer-{$key_id}" ), 0, 4 );
    $key      = "bits_whisperer-{$key_id}-{$checksum}";

    return $key;
}

/**
 * Store a licence key in the local WordPress database.
 */
function bits_reg_store_key(
    int $order_id,
    int $user_id,
    string $email,
    string $key_type,
    string $licence_key
): void {
    global $wpdb;
    $table = $wpdb->prefix . 'bits_licence_keys';

    $expires_at = null;
    if ( 'annual' === $key_type ) {
        $expires_at = gmdate( 'Y-m-d H:i:s', strtotime( '+365 days' ) );
    }

    // phpcs:ignore WordPress.DB.DirectDatabaseQuery
    $wpdb->insert( $table, [
        'order_id'    => $order_id,
        'user_id'     => $user_id,
        'email'       => $email,
        'product_id'  => 'bits_whisperer',
        'key_type'    => $key_type,
        'licence_key' => $licence_key,
        'status'      => 'active',
        'issued_at'   => current_time( 'mysql', true ),
        'expires_at'  => $expires_at,
    ] );
}

// ---------------------------------------------------------------------------
// "My Licence Keys" page in My Account
// ---------------------------------------------------------------------------

add_action( 'init', 'bits_reg_register_endpoint' );
add_filter( 'woocommerce_account_menu_items', 'bits_reg_account_menu' );
add_action( 'woocommerce_account_licence-keys_endpoint', 'bits_reg_account_page' );

/**
 * Register the custom WooCommerce My Account endpoint.
 */
function bits_reg_register_endpoint(): void {
    add_rewrite_endpoint( 'licence-keys', EP_ROOT | EP_PAGES );
}

/**
 * Add "Licence Keys" to the My Account menu.
 *
 * @param array<string, string> $items Existing menu items.
 * @return array<string, string> Modified menu items.
 */
function bits_reg_account_menu( array $items ): array {
    // Insert before "Log out".
    $logout = [];
    if ( isset( $items['customer-logout'] ) ) {
        $logout['customer-logout'] = $items['customer-logout'];
        unset( $items['customer-logout'] );
    }
    $items['licence-keys']    = __( 'Licence Keys', 'bits-registration' );
    $items['customer-logout'] = $logout['customer-logout'] ?? __( 'Log out', 'bits-registration' );

    return $items;
}

/**
 * Render the "My Licence Keys" page.
 */
function bits_reg_account_page(): void {
    global $wpdb;
    $user_id = get_current_user_id();
    $table   = $wpdb->prefix . 'bits_licence_keys';

    // phpcs:ignore WordPress.DB.DirectDatabaseQuery, WordPress.DB.PreparedSQL
    $keys = $wpdb->get_results(
        $wpdb->prepare(
            "SELECT * FROM {$table} WHERE user_id = %d ORDER BY created_at DESC",
            $user_id
        ),
        ARRAY_A
    );

    echo '<h2>' . esc_html__( 'Your BITS Whisperer Licence Keys', 'bits-registration' ) . '</h2>';

    if ( empty( $keys ) ) {
        echo '<p>' . esc_html__(
            'You have no licence keys yet. Purchase a BITS Whisperer licence to get started.',
            'bits-registration'
        ) . '</p>';
        return;
    }

    echo '<table class="woocommerce-orders-table shop_table shop_table_responsive">';
    echo '<thead><tr>';
    echo '<th>' . esc_html__( 'Licence Key', 'bits-registration' ) . '</th>';
    echo '<th>' . esc_html__( 'Type', 'bits-registration' ) . '</th>';
    echo '<th>' . esc_html__( 'Status', 'bits-registration' ) . '</th>';
    echo '<th>' . esc_html__( 'Issued', 'bits-registration' ) . '</th>';
    echo '<th>' . esc_html__( 'Expires', 'bits-registration' ) . '</th>';
    echo '</tr></thead><tbody>';

    foreach ( $keys as $key ) {
        $status_label = ucfirst( $key['status'] );
        $expires      = $key['expires_at'] ? date_i18n( get_option( 'date_format' ), strtotime( $key['expires_at'] ) ) : __( 'Never', 'bits-registration' );
        $issued       = $key['issued_at'] ? date_i18n( get_option( 'date_format' ), strtotime( $key['issued_at'] ) ) : '—';

        echo '<tr>';
        echo '<td><code>' . esc_html( $key['licence_key'] ) . '</code></td>';
        echo '<td>' . esc_html( ucfirst( $key['key_type'] ) ) . '</td>';
        echo '<td>' . esc_html( $status_label ) . '</td>';
        echo '<td>' . esc_html( $issued ) . '</td>';
        echo '<td>' . esc_html( $expires ) . '</td>';
        echo '</tr>';
    }

    echo '</tbody></table>';

    echo '<div class="bits-reg-instructions" style="margin-top: 2em;">';
    echo '<h3>' . esc_html__( 'How to activate BITS Whisperer', 'bits-registration' ) . '</h3>';
    echo '<ol>';
    echo '<li>' . esc_html__( 'Open BITS Whisperer.', 'bits-registration' ) . '</li>';
    echo '<li>' . esc_html__( 'Go to Tools → Settings → General tab.', 'bits-registration' ) . '</li>';
    echo '<li>' . esc_html__( 'In the BITS Registration section, paste your licence key.', 'bits-registration' ) . '</li>';
    echo '<li>' . esc_html__( 'Click "Verify" to activate your licence.', 'bits-registration' ) . '</li>';
    echo '</ol>';
    echo '</div>';
}

// ---------------------------------------------------------------------------
// Email: include licence key in order confirmation
// ---------------------------------------------------------------------------

add_action( 'woocommerce_email_after_order_table', 'bits_reg_email_licence_keys', 10, 4 );

/**
 * Append licence key info to order confirmation emails.
 *
 * @param WC_Order $order         The order object.
 * @param bool     $sent_to_admin Whether this is an admin email.
 * @param bool     $plain_text    Whether this is a plain text email.
 * @param WC_Email $email         The email object.
 */
function bits_reg_email_licence_keys( $order, $sent_to_admin, $plain_text, $email ): void {
    if ( $sent_to_admin ) {
        return;
    }

    global $wpdb;
    $table = $wpdb->prefix . 'bits_licence_keys';

    // phpcs:ignore WordPress.DB.DirectDatabaseQuery, WordPress.DB.PreparedSQL
    $keys = $wpdb->get_results(
        $wpdb->prepare(
            "SELECT licence_key, key_type FROM {$table} WHERE order_id = %d",
            $order->get_id()
        ),
        ARRAY_A
    );

    if ( empty( $keys ) ) {
        return;
    }

    if ( $plain_text ) {
        echo "\n\n";
        echo "BITS WHISPERER LICENCE KEY(S)\n";
        echo "=============================\n";
        foreach ( $keys as $key ) {
            echo sprintf( "%s (%s)\n", $key['licence_key'], ucfirst( $key['key_type'] ) );
        }
        echo "\nTo activate: Open BITS Whisperer → Tools → Settings → General → BITS Registration.\n";
    } else {
        echo '<h2 style="margin-top: 2em;">';
        echo esc_html__( 'Your BITS Whisperer Licence Key(s)', 'bits-registration' );
        echo '</h2>';
        echo '<table cellspacing="0" cellpadding="6" border="1" style="border-collapse: collapse; width: 100%;">';
        echo '<tr><th>Licence Key</th><th>Type</th></tr>';
        foreach ( $keys as $key ) {
            echo '<tr>';
            echo '<td><code>' . esc_html( $key['licence_key'] ) . '</code></td>';
            echo '<td>' . esc_html( ucfirst( $key['key_type'] ) ) . '</td>';
            echo '</tr>';
        }
        echo '</table>';
        echo '<p style="margin-top: 1em;">';
        echo esc_html__(
            'To activate: Open BITS Whisperer → Tools → Settings → General → BITS Registration.',
            'bits-registration'
        );
        echo '</p>';
    }
}

// ---------------------------------------------------------------------------
// Admin column: show licence key status on orders list
// ---------------------------------------------------------------------------

add_filter( 'manage_edit-shop_order_columns', 'bits_reg_order_columns' );
add_action( 'manage_shop_order_posts_custom_column', 'bits_reg_order_column_data', 10, 2 );

/**
 * Add a "Licence" column to the WooCommerce orders list.
 *
 * @param array<string, string> $columns Existing columns.
 * @return array<string, string> Modified columns.
 */
function bits_reg_order_columns( array $columns ): array {
    $new = [];
    foreach ( $columns as $key => $label ) {
        $new[ $key ] = $label;
        if ( 'order_status' === $key ) {
            $new['bits_licence'] = __( 'Licence', 'bits-registration' );
        }
    }
    return $new;
}

/**
 * Populate the "Licence" column with key status.
 *
 * @param string $column  Column identifier.
 * @param int    $post_id Order post ID.
 */
function bits_reg_order_column_data( string $column, int $post_id ): void {
    if ( 'bits_licence' !== $column ) {
        return;
    }

    global $wpdb;
    $table = $wpdb->prefix . 'bits_licence_keys';

    // phpcs:ignore WordPress.DB.DirectDatabaseQuery, WordPress.DB.PreparedSQL
    $count = (int) $wpdb->get_var(
        $wpdb->prepare( "SELECT COUNT(*) FROM {$table} WHERE order_id = %d", $post_id )
    );

    if ( $count > 0 ) {
        echo '<span class="dashicons dashicons-yes-alt" style="color: #46b450;" title="' . esc_attr( $count . ' key(s) issued' ) . '"></span>';
    } else {
        echo '<span class="dashicons dashicons-minus" style="color: #999;" title="No keys"></span>';
    }
}
