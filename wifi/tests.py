import base64
import io
import os
import xml.etree.ElementTree as ET
from unittest import mock
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import TestCase, tag, override_settings, Client
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from django.contrib.auth.models import User
from django.urls import reverse

from PIL import Image, ImageDraw
from pyzbar.pyzbar import decode
from tests.selenium_helpers import click_until, get_chrome_options, login_from_page

from wifi.views import qr_svg

def _rasterize_qr_svg(svg, scale=12):
    """Rasterize the SVG from wifi.views.qr_svg (circles, finder rects and the
    nested logo <svg>) with PIL. The logo area is painted solid black, the
    worst case a scanner can see there."""
    ns = "{http://www.w3.org/2000/svg}"
    root = ET.fromstring(svg)
    n = float(root.get("viewBox").split()[2])
    img = Image.new("L", (int(n * scale), int(n * scale)), 255)
    draw = ImageDraw.Draw(img)
    for el in root.iter():
        if el.tag == ns + "circle":
            cx, cy, r = (float(el.get(k)) * scale for k in ("cx", "cy", "r"))
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=0)
        elif el.tag == ns + "rect" and el.get("x") is not None:
            x, y, w, h = (float(el.get(k)) * scale for k in ("x", "y", "width", "height"))
            if el.get("fill") == "none":
                sw = float(el.get("stroke-width")) * scale
                draw.rectangle([x - sw / 2, y - sw / 2, x + w + sw / 2, y + h + sw / 2], outline=0, width=int(sw))
            else:
                draw.rectangle([x, y, x + w, y + h], fill=0)
        elif el.tag == ns + "svg" and el is not root:
            x, y, w = (float(el.get(k)) * scale for k in ("x", "y", "width"))
            draw.rectangle([x, y, x + w, y + w], fill=0)
    return img


def _decode_data_uri_svg(content):
    """Decode the QR code image (img.qr-code) in a page. Other SVG data URIs,
    like the hub's monogram in the header, are skipped."""
    start = content.find('class="qr-code"')
    assert start != -1, "QR code image not found"
    start = content.rfind("<img", 0, start)
    start = content.find(SVG_DATA_URI, start)
    assert start != -1, "QR code SVG data URI not found"
    start += len(SVG_DATA_URI)
    svg = base64.b64decode(content[start:content.find('"', start)]).decode("utf-8")
    return [d.data.decode("utf-8") for d in decode(_rasterize_qr_svg(svg))]


def _decode_element(img_element):
    """Decode the QR code as the browser rendered it, logo included."""
    image = Image.open(io.BytesIO(img_element.screenshot_as_png))
    decoded = decode(image)
    assert decoded, "No QR code detected in the rendered image"
    return decoded[0].data.decode("utf-8")


SVG_DATA_URI = "data:image/svg+xml;base64,"


class WifiQRGenerationTests(TestCase):
    def setUp(self):
        self.client = Client()

    @override_settings(
        WIFI_NETWORKS_PUBLIC=["TestNetwork"],
        WIFI_PASSWORD_FOR_TESTNETWORK="testpass123",
    )
    def test_qr_code_generation_with_env_variables(self):
        response = self.client.get("/wifi/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertEqual(_decode_data_uri_svg(content), ["WIFI:S:TestNetwork;T:WPA;P:testpass123;;"])

    def test_qr_with_logo_scans_for_long_passwords(self):
        """Longer payloads need bigger QR versions; the logo hole scales with
        them and must stay within what error correction can recover."""
        for password in ("x", "correct-horse-battery-staple-" * 3):
            text = f"WIFI:S:Black Diamond Lodge Guest;T:WPA;P:{password};;"
            decoded = [d.data.decode("utf-8") for d in decode(_rasterize_qr_svg(qr_svg(text)))]
            self.assertEqual(decoded, [text])

    @override_settings(WIFI_NETWORKS_PUBLIC=["Guest"], WIFI_NETWORKS_AUTH=["Private"])
    def test_private_networks_are_admin_only(self):
        def ssids():
            return [q["ssid"] for q in self.client.get("/wifi/").context["qr_codes"]]

        self.assertEqual(ssids(), ["Guest"])
        user = User.objects.create_user(username="member", password="pw")
        self.client.force_login(user)
        self.assertEqual(ssids(), ["Guest"])
        user.is_staff = True
        user.save()
        self.assertEqual(ssids(), ["Private"])

    def test_qr_embeds_monogram(self):
        self.assertIn('class="qr-logo"', qr_svg("WIFI:S:x;T:WPA;P:y;;"))

@tag('selenium')
@override_settings(
    WIFI_NETWORKS_PUBLIC=["TestNetwork","TestNetwork2"],
    WIFI_NETWORKS_AUTH=["TestNetworkAuth","TestNetworkAuth2"],
    WIFI_PASSWORD_FOR_TESTNETWORK="testpass123",
    WIFI_PASSWORD_FOR_TESTNETWORK2="testpass1232",
    WIFI_PASSWORD_FOR_TESTNETWORKAUTH="testpass1233",
    WIFI_PASSWORD_FOR_TESTNETWORKAUTH2="testpass1234",
)
class WifiQRPageSeleniumTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.driver = webdriver.Chrome(options=get_chrome_options())
        cls.driver.set_window_size(1920, 1080)
        
    @classmethod
    def tearDownClass(cls):
        cls.driver.quit()
        super().tearDownClass()
        
    def setUp(self):
        # Reset browser state between tests
        self.driver.get('about:blank')
        self.driver.delete_all_cookies()

        self.test_user = User.objects.create_user(username='testuser', password='testpassword', is_staff=True)
        
    def test_wifi_page_title_and_header(self):
        """Verify that the wifi page title and header are correct."""
        self.driver.get(f'{self.live_server_url}/wifi/')
        header = WebDriverWait(self.driver, 20).until(
            EC.presence_of_element_located((By.TAG_NAME, "h1"))
        )
        self.assertEqual(header.get_attribute("textContent").strip(), "WiFi Networks")
        
    # def test_qr_codes_container_is_centered(self):
    #     """
    #     Verify that the container holding the QR codes is centered both vertically and horizontally.
    #     """
    #     self.driver.get(f'{self.live_server_url}/wifi/')
        
    #     self.driver.save_screenshot("screenshot.png")
        
    #     # Wait for the container to be present. Adjust the selector if necessary.
    #     container = self.driver.find_element(By.CSS_SELECTOR, '.container.full-height')
        
    #     # Get the container's bounding rectangle.
    #     container_rect = container.rect  # returns {'height': ..., 'width': ..., 'x': ..., 'y': ...}
        
    #     # Get the window size.
    #     window_size = self.driver.get_window_size()  # returns dict with keys 'width' and 'height'
        
    #     # Calculate expected x and y positions for centering.
    #     expected_x = (window_size['width'] - container_rect['width']) / 2
    #     expected_y = (window_size['height'] - container_rect['height']) / 2
        
    #     # Allow a small tolerance for differences due to rendering.
    #     tolerance = 10  # pixels
        
    #     self.assertAlmostEqual(
    #         container_rect['x'], 
    #         expected_x, 
    #         delta=tolerance, 
    #         msg=f"Container is not centered horizontally. Expected x ~{expected_x}, got {container_rect['x']}"
    #     )
        
    #     self.assertAlmostEqual(
    #         container_rect['y'], 
    #         expected_y, 
    #         delta=tolerance, 
    #         msg=f"Container is not centered vertically. Expected y ~{expected_y}, got {container_rect['y']}"
    #     )        
        
    def test_wifi_page_no_auth_qr_codes(self):
        """Verify that no QR codes for authenticated networks are displayed for unauthenticated users."""
        self.driver.get(f'{self.live_server_url}/wifi/')
        # Wait for QR code images to load
        WebDriverWait(self.driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "img.qr-code"))
        )
        # Find all QR code images.
        qr_images = self.driver.find_elements(By.CSS_SELECTOR, "img.qr-code")
        self.assertGreater(len(qr_images), 0, "No QR code images found on the page")
        
        # Define the expected auth QR texts that should NOT be present.
        auth_qr_texts = {
            f"WIFI:S:TestNetworkAuth;T:WPA;P:testpass1233;;",
            f"WIFI:S:TestNetworkAuth2;T:WPA;P:testpass1234;;"
        }
        
        # Iterate through each found QR code image.
        for img in qr_images:
            decoded_text = _decode_element(img)
            
            # Ensure no auth network QR data is present.
            self.assertNotIn(
                decoded_text,
                auth_qr_texts,
                f"Auth QR code '{decoded_text}' should not be displayed for non-authenticated users"
            )
        
    def test_wifi_page_public_qr_code(self):
        """Verify that the public QR code is displayed correctly."""
        self.driver.get(f'{self.live_server_url}/wifi/')
        
        # Wait for QR code images to load
        WebDriverWait(self.driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "img.qr-code"))
        )
        # Verify that at least one QR code image is present.
        qr_images = self.driver.find_elements(By.CSS_SELECTOR, "img.qr-code")
        self.assertGreater(len(qr_images), 0, "No QR code images found on the page")
        
        # Optionally, assert that each found image has valid dimensions and correct QR data.
        expected_qr_texts = {
            f"WIFI:S:TestNetwork;T:WPA;P:testpass123;;",
            f"WIFI:S:TestNetwork2;T:WPA;P:testpass1232;;"
        }
        found_qr_texts = set()

        for img in qr_images:
            # Ensure the image has non-zero width.
            width = img.size.get("width", 0)
            self.assertGreater(width, 0, f"Image width should be > 0 but got {width}")

            decoded_text = _decode_element(img)
            self.assertIn(
                decoded_text,
                expected_qr_texts,
                f"Decoded QR text '{decoded_text}' not one of the expected values."
            )
            found_qr_texts.add(decoded_text)

        # Verify that we found all expected QR codes.
        self.assertEqual(found_qr_texts, expected_qr_texts, "Not all expected QR codes were found.")
        
    def test_wifi_page_login_redirects_back_to_wifi(self):
        """
        Test that after logging in, the user is redirected back to the wifi page.
        """
       
        self.driver.get(f"{self.live_server_url}/wifi/")
        
        # Log in using shared helper
        login_from_page(self.driver, self.live_server_url)
        
        # Wait for redirect back to wifi page
        WebDriverWait(self.driver, 20).until(
            EC.url_contains("/wifi/")
        )
        
        # Check that the current URL is the wifi page.
        self.assertIn("/wifi/", self.driver.current_url)
        
    def test_wifi_page_logout_redirects_back_to_wifi(self):
        """
        Test that after logging out, the user is redirected back to the wifi page.
        """
     
        self.driver.get(f"{self.live_server_url}/wifi/")
        
        # Log in using shared helper
        login_from_page(self.driver, self.live_server_url)
        
        # Sign out lives in the account menu, so open that first.
        click_until(self.driver, (By.ID, 'user-menu-button'),
                    lambda d: d.find_element(By.ID, 'logout-button').is_displayed())
        click_until(self.driver, (By.ID, 'logout-button'),
                    EC.presence_of_element_located((By.ID, 'login-button')), settle=10)

        self.assertIn("/wifi/", self.driver.current_url)
        
    def test_wifi_page_no_public_qr_codes(self):
        """
        Log in a test user and verify that none of the public QR codes are present.
        """
       
        self.driver.get(f"{self.live_server_url}/wifi/")
        
        # Log in using shared helper
        login_from_page(self.driver, self.live_server_url)
        
        # Wait for redirect back to wifi page and QR codes to load
        WebDriverWait(self.driver, 20).until(
            EC.url_contains("/wifi/")
        )
        WebDriverWait(self.driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "img.qr-code"))
        )
    
        qr_images = self.driver.find_elements(By.CSS_SELECTOR, "img.qr-code")
        self.assertGreater(len(qr_images), 0, "No QR code images found on the page")
        
        # Define the expected public QR texts that should NOT be present after login.
        public_qr_texts = {
            f"WIFI:S:TestNetwork;T:WPA;P:testpass123;;",
            f"WIFI:S:TestNetwork2;T:WPA;P:testpass1232;;"
        }
        
        for img in qr_images:
            decoded_text = _decode_element(img)

            # Ensure that the decoded text is not one of the public QR codes.
            self.assertNotIn(
                decoded_text,
                public_qr_texts,
                f"Public QR code '{decoded_text}' should not be displayed for authenticated users"
            )        
        
    
    def test_wifi_page_auth_qr_codes(self):
        """
        Log in a test user and verify that the auth QR codes are present.
        """
        
        self.driver.get(f"{self.live_server_url}/wifi/")
        
        # Log in using shared helper
        login_from_page(self.driver, self.live_server_url)
        
        # Wait for redirect back to wifi page
        WebDriverWait(self.driver, 20).until(
            EC.url_contains("/wifi/")
        )
        
        # Wait for QR code images to load
        WebDriverWait(self.driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "img.qr-code"))
        )
        
        qr_images = self.driver.find_elements(By.CSS_SELECTOR, "img.qr-code")
        self.assertGreater(len(qr_images), 0, "No QR code images found on the page")
        
        # Expected auth QR texts based on overridden settings.
        expected_auth_qr_texts = {
            f"WIFI:S:TestNetworkAuth;T:WPA;P:testpass1233;;",
            f"WIFI:S:TestNetworkAuth2;T:WPA;P:testpass1234;;"
        }
        found_auth_qr_texts = set()
        
        for img in qr_images:
            decoded_text = _decode_element(img)
            
            if decoded_text in expected_auth_qr_texts:
                found_auth_qr_texts.add(decoded_text)
        
        self.assertEqual(
            found_auth_qr_texts,
            expected_auth_qr_texts,
            "Not all expected auth QR codes were found on the logged in page."
        )

class WifiSettingsTests(TestCase):
    @mock.patch.dict(os.environ, {
        "BDH_WIFI_NETWORKS_PUBLIC": "Lodge Guest, Other",
        "BDH_WIFI_PASSWORD_FOR_LODGE_GUEST": "s3cret",
    })
    def test_namespaced_env_settings(self):
        response = Client().get(reverse("wifi_qr"))
        self.assertEqual(response.status_code, 200)
        codes = {c["ssid"]: c["password"] for c in response.context["qr_codes"]}
        self.assertEqual(codes, {"Lodge Guest": "s3cret", "Other": "password"})

    @mock.patch.dict(os.environ, {
        "WIFI_NETWORKS_PUBLIC": "legacy_net",
        "WIFI_PASSWORD_FOR_LEGACY_NET": "old-name",
    })
    def test_legacy_env_names_still_work(self):
        response = Client().get(reverse("wifi_qr"))
        codes = {c["ssid"]: c["password"] for c in response.context["qr_codes"]}
        self.assertEqual(codes, {"legacy_net": "old-name"})
