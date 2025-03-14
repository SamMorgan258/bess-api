from fastapi import FastAPI, Query
from bs4 import BeautifulSoup
import requests
import urllib.parse
import pandas as pd
import time

app = FastAPI()

# Maintain a session for requests
session = requests.Session()

# Base URL of the BESS website
BASE_URL = "http://bess.illinois.edu/"

def select_frequency(frequency: str):
    """Selects 50 Hz or 60 Hz on the BESS website."""
    url_current = BASE_URL + "current.asp"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": BASE_URL,
        "Origin": BASE_URL,
        "Content-Type": "application/x-www-form-urlencoded",
    }

    response_current = session.get(url_current, headers=headers)

    if response_current.status_code != 200:
        return None

    form_data = {"50 hz": "50 hz"} if frequency == "50" else {"60 hz": "60 hz (North America)"}
    url_search = BASE_URL + "search.asp"
    response_search = session.post(url_search, data=form_data, headers=headers)

    return response_search if response_search.status_code == 200 else None

def get_power_options(response_search):
    """Extracts all power supply options."""
    soup = BeautifulSoup(response_search.text, "html.parser")
    power_dropdown = soup.find("select", {"name": "power"})
    return [option.text.strip() for option in power_dropdown.find_all("option")]

def scrape_fan_data(frequency, power_options):
    """Scrapes fan data and captures PDF links."""
    all_data = []
    
    for power in power_options:
        power = power.split(",")[0].strip()
        manufacturer = "All Manufacturers"
        url_results = BASE_URL + "searchResults2.asp"
        
        form_data = {
            "hz": frequency,
            "power": power,
            "manufacturer": manufacturer,
            "fansize": "Any Size",
            "airflow": "Any Airflow",
            "VER": "Any VER",
            "Submit": "Submit",
        }
        
        response_results = session.post(url_results, data=form_data)
        if response_results.status_code != 200:
            continue

        soup_results = BeautifulSoup(response_results.text, "html.parser")
        tables = soup_results.find_all("table")
        if len(tables) < 4:
            continue

        table = tables[3]  # Table 4 is at index 3
        rows = table.find_all("tr")
        manufacturer_name = ""

        for row in rows:
            columns = row.find_all("td")
            data = [col.text.strip() for col in columns]

            if len(data) == 1:
                manufacturer_name = data[0]
                continue

            pdf_link = ""
            if len(columns) > 0:
                link_tag = columns[0].find("a")
                if link_tag and "href" in link_tag.attrs:
                    pdf_link = urllib.parse.urljoin(BASE_URL, link_tag["href"])

            if len(data) >= 10:
                all_data.append({
                    "frequency": f"{frequency} Hz",
                    "manufacturer": manufacturer_name,
                    "power": power,
                    "test_pdf": pdf_link,
                    "test_id": data[0],
                    "model": data[1],
                    "size": data[2],
                    "cone": data[3],
                    "shutter": data[4],
                    "airflow_0.05_sp": data[5],
                    "ver_0.05_sp": data[6],
                    "airflow_0.10_sp": data[7],
                    "ver_0.10_sp": data[8],
                    "airflow_ratio": data[9],
                })
        
        time.sleep(1)  # Avoid overwhelming the server
    
    return all_data

@app.get("/bess-data")
def get_bess_data(frequency: str = Query(..., description="Specify '50' or '60' for Hz")):
    """API endpoint to get BESS fan test data."""
    if frequency not in ["50", "60"]:
        return {"error": "Invalid frequency. Use '50' or '60'."}

    response_search = select_frequency(frequency)
    if not response_search:
        return {"error": "Failed to connect to BESS site."}

    power_options = get_power_options(response_search)
    fan_data = scrape_fan_data(frequency, power_options)

    return {"data": fan_data}

@app.get("/bess-pdf")
def get_test_pdf(test_id: str = Query(..., description="Test ID to fetch the corresponding PDF link")):
    """API endpoint to get the PDF link for a specific test."""
    response_search = select_frequency("50")
    if not response_search:
        return {"error": "Failed to connect to BESS site."}

    power_options = get_power_options(response_search)
    fan_data = scrape_fan_data("50", power_options) + scrape_fan_data("60", power_options)

    for test in fan_data:
        if test["test_id"] == test_id:
            return {"test_id": test_id, "pdf_link": test["test_pdf"]}

    return {"error": "Test ID not found."}

