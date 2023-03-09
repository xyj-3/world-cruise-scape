#!/usr/bin/env python

import json
import re
import requests
import textwrap
from datetime import datetime
from bs4 import BeautifulSoup

# -------------------------------------------------------------------------------------------------------------------- #
# The purpose of this program is to reference the article at https://www.cruisecritic.com/articles.cfm?ID=514 and
# extract the useful information into a JSON structure. It requires python 3.6 and bs4.

# The page itself was generally well-structured for a web page, making it easier to parse. There were some
# inconsistencies.
# No price: Princess Cruises - Coral Princess (2024)
# There were some cases unable to be captured by generalized regex, processed by manual dicts
# -------------------------------------------------------------------------------------------------------------------- #

if __name__ == "__main__":
    # use the local saved copy
    with open("Best World Cruises of 2023, 2024 and 2025 _ Cruise Critic.html", "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")
    # print(soup.prettify())

    # or open webpage using http request, works for the version Updated December 05, 2022
    # url = "https://www.cruisecritic.com/articles.cfm?ID=514"
    # response = requests.get(url)
    # soup = BeautifulSoup(response.content, "html.parser")

    # get variables required for processing
    year_headings = soup.find_all("h2", string=lambda text: text and '20' in text)
    cruise_headings = soup.find_all("h3")[:-2]  # the headings identifying individual world cruises

    year_dict = {}
    for i in range(len(year_headings)):
        year_dict[str(2023 + i)] = year_headings[i]
    ship_name_dict = {}  # for caching ship names because they tend to remain same year over year
    # exception dictionaries for the cases that could not be covered by regex
    title_exception_dict = {"Oceania": "Oceania Cruises"}
    ship_name_exception_dict = {
        "MSC Cruises (2024)": ["MSC Poesia"],
        "Viking Cruises (2024)": ["Viking Sky", "Viking Neptune"]
    }
    departure_loc_exception_dict = {
        "Cunard Line - Queen Mary 2 (2024)": ["New York"],
        "Cunard Line - Queen Victoria (2024)": ["Hamburg", "Southampton"],
        "Princess Cruises - Island Princess (2024)": ["Fort Lauderdale", "Los Angeles"]
    }
    departure_date_exception_dict = {
        "Princess Cruises (2023)": ["January 5, 2023", "January 19, 2023"],
        "Princess Cruises - Island Princess (2024)": ["January 4, 2024", "January 18, 2024"]
    }

    data = {}  # data to be saved as json

    for cruise_heading in cruise_headings:  # cruise_heading is a bs4 Tag
        # THE CRUISE
        year_string = cruise_heading.parent.find_previous_sibling(lambda prev_sibling: prev_sibling.string and re.match(
            r"^202[3-5] World Cruises", prev_sibling.string)).string.split()[0]  # get the first prev sibling that has
        # r"^202[3-5] World Cruises" in its string and get the year from that
        if cruise_heading.string in title_exception_dict:
            cruise_heading.string = title_exception_dict[cruise_heading.string]
        title = f"{cruise_heading.string} ({year_string})"
        # print(title)

        # DESCRIPTION
        description = ""
        description_tag = cruise_heading.parent.next_sibling
        while "The Trip: " not in description_tag.get_text():
            description_tag = description_tag.next_sibling
        first_description_tag = description_tag  # save to find ship name
        # get the entire description split over multiple tags
        while "Departure Date: " not in description_tag.get_text():
            description += " " + description_tag.get_text()
            description_tag = description_tag.next_sibling
        description = description.replace(" The Trip: ", "")

        # SHIP NAME
        ship_name = []
        match = re.search(r"[a-zA-Z]* - ([a-zA-Z0-9 ]*)", cruise_heading.string)
        if match:  # first try searching if the ship name is in the title
            ship_name = [match.group(1)]
            ship_name_dict[cruise_heading.string] = ship_name
        elif title in ship_name_exception_dict:
            ship_name = ship_name_exception_dict[title]
        else:  # otherwise start searching in the description for a link that contains the ship name
            links = first_description_tag.find_all("a")
            links = [re.sub(r"(’s|'s?)", "", link.string) for link in links]  # one link is "Oceania'"
            links = [s for s in links if s not in title]  # remove cruise line name links
            if len(links) != 0:
                ship_name = links
                ship_name_dict[cruise_heading.string] = ship_name
            elif cruise_heading.string in ship_name_dict:  # use ship_name cache
                ship_name = ship_name_dict[cruise_heading.string]

        # DEPARTURE DATE
        departure_tag = description_tag  # because of the next_sibling loop for description
        while "Departure Date: " not in departure_tag.get_text():
            departure_tag = departure_tag.next_sibling
        departure = departure_tag.get_text()
        if title in departure_date_exception_dict:
            departure_date = departure_date_exception_dict[title]
        else:
            departure_date = re.findall(r"([A-Z][a-z]+ [1-3]?\d, \d{4})", departure)
        # for converting the date from long-form to iso 8601
        # departure_date = [datetime.strptime(date, "%B %d, %Y").strftime("%Y-%m-%dT%H:%M:%S.%fZ") for date in departure_date]

        # SEGMENTS
        segments_tag = departure_tag.next_sibling
        while "Itinerary Segments: " not in segments_tag.get_text():
            segments_tag = segments_tag.next_sibling
        segments = segments_tag.get_text().replace("Itinerary Segments: ", "")
        matches = segments.split("; ")
        matches = [re.search(r"([a-zA-Z ]+) \(([a-z0-9 ]+)\)", match) for match in matches]
        if None not in matches:
            segments_dict = {match.group(1): int(match.group(2).split()[0]) for match in matches}
        else:  # no segments provided
            segments_dict = {}

        # NUMBER OF DAYS
        match = re.search(r"(\d+)(?:\s|-)(?:day|night|days|nights)", description)
        days = int(match.group(1)) if match else None
        if days is None:
            # search for the highest number in itinerary segments
            nums = re.findall(r"\d+", segments)
            nums = [int(num) for num in nums]
            if len(nums) != 0:
                days = max(nums)

        # DEPARTURE LOCATION
        if title in departure_loc_exception_dict:
            departure_loc = departure_loc_exception_dict[title]
        else:
            # check departure locations in the departure tag for regex "from/departs/in X"
            # one group (?:\([A-Z][a-z]+\))? is just to capture the (Brooklyn) part of New York (Brooklyn)
            departure_loc = re.findall(r"(?:from|departs|in) ((?:[A-Z][a-z]+\s?)+(?:\([A-Z][a-z]+\))?)", departure)
            if not departure_loc:
                # check departure locations in the departure tag for regex "roundtrip from X"
                departure_loc = re.findall(r"roundtrip from ((?:[A-Z][a-z]+\s?)+)", description)
            if not departure_loc:
                # check departure locations in the description or segments for regex "X to X"
                # only get first match for this because there are usually multiple segments
                match = re.search(r"((?:[A-Z][a-z]+\s?)+) to (?:[A-Z][a-z]+\s?)+", description + segments)
                departure_loc = [match.group(1)] if match else []

        # PRICE
        price_tag = segments_tag.next_sibling
        while "Price: " not in price_tag.get_text():
            price_tag = price_tag.next_sibling
        match = re.search(r"\$\s?\d{1,3}(?:,\d{3})*", price_tag.get_text())
        price = match.group(0).replace(" ", "") if match else ""

        # add entry to the data
        data[title] = {
            "price": price,
            "days": days,
            "description": description,
            "dep_loc": departure_loc,
            "dep_date": departure_date,
            "ship": ship_name,
            "segments": segments_dict,
        }

    # dump the info as a JSON file
    out_file = "world-cruises.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    # for printing
    # json_data = json.dumps(data, indent=2)  # format as a json
    # wrapped_json_data = '\n'.join(
    #     [line for string in json_data.split('\n') for line in textwrap.wrap(string, width=80)])
    # print(wrapped_json_data)
