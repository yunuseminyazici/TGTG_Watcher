from tgtg import TgtgClient
from json import load
import requests
import schedule
import time
import os
import traceback
import maya
import datetime
from urllib.parse import quote


credentials_remote_loaded = False

try:
    # Credential handling heroku
    credentials = dict()
    credentials['email'] = os.environ['TGTG_EMAIL']
    print(f"tgtg_email: {credentials['email']}")
    credentials['password'] = os.environ['TGTG_PW']
    print(f"tgtg_pw: {credentials['password']}")

    telegram = dict()
    telegram['bot_chatID1'] = os.environ['TELEGRAM_BOT_CHATID1']
    print(f"TELEGRAM_BOT_CHATID1: {telegram['bot_chatID1']}")

    telegram['bot_token'] = os.environ['TELEGRAM_BOT_TOKEN']
    print(f"TELEGRAM_BOT_TOKEN: {telegram['bot_token']}")

    credentials_remote_loaded = True

except:
    print("No credentials found in Heroku environment")

if not credentials_remote_loaded:
    try:
        # Load credentials from a file
        f = open('config.json', 'r')
        config = load(f)
        f.close()
        print("Credentials loaded from a file")

    except FileNotFoundError:
        print("No files found for local credentials.")
        exit(1)

    except:
        print("Unexpected error")
        print(traceback.format_exc())
        exit(1)

try:
    # Create the tgtg client with my credentials
    client = TgtgClient(access_token=config['tgtg']['access_token'],
                        refresh_token=config['tgtg']['refresh_token'],
                        user_id=config['tgtg']['user_id'])

except KeyError:
    print(f"Failed to obtain TGTG credentials")
    exit(1)

try:
    bot_token = config['telegram']["bot_token"]
except KeyError:
    print(f"Failed to obtain Telegram bot token")
    exit(1)
try:
    bot_chatID = config['telegram']["bot_chatID"]
except KeyError:
    print(f"Failed to obtain Telegram bot chatID")
    exit(1)

# Init the favourites in stock list as a global variable
favourites_in_stock = list()


def telegram_bot_send_text(bot_message):
    send_text = 'https://api.telegram.org/bot' + bot_token + '/sendMessage?chat_id=' + bot_chatID + '&parse_mode=Markdown&text=' + bot_message
    response = requests.get(send_text)

    return response.json()


def telegram_bot_send_image(image_url, image_caption=None):
    send_photo = 'https://api.telegram.org/bot' + bot_token + '/sendPhoto?chat_id=' + bot_chatID + '&photo=' + image_url

    if image_caption is not None:
        send_photo += '&parse_mode=Markdown&caption=' + quote(image_caption)
    response = requests.get(send_photo)

    return response.json()


def extract_api_result(api_result):
    """Parse raw API and store important information"""
    new_api_result = list()

    for store in api_result:
        current_fav = dict()
        current_fav['item_id'] = store['item']['item_id']
        current_fav['items_available'] = store['items_available']
        current_fav['category_picture'] = store['store']['cover_picture']['current_url']
        current_fav['display_name'] = store['display_name']
        current_fav['address_line'] = store['pickup_location']['address']['address_line']
        current_fav['latitude'] = store['pickup_location']['location']['latitude']
        current_fav['longitude'] = store['pickup_location']['location']['longitude']
        current_fav['description'] = store['item']['description']
        current_fav['price_including_taxes'] = str(store['item']['price_including_taxes']['minor_units'])[
                                               :-(store['item']['price_including_taxes']['decimals'])] + "." + str(
            store['item']['price_including_taxes']['minor_units'])[-(
            store['item']['price_including_taxes']['decimals']):] + store['item']['price_including_taxes']["code"]

        current_fav['value_including_taxes'] = str(store['item']['value_including_taxes']['minor_units'])[
                                               :-(store['item']['value_including_taxes']['decimals'])] + "." + str(
            store['item']['value_including_taxes']['minor_units'])[-(
            store['item']['value_including_taxes']['decimals']):] + store['item']['value_including_taxes']['code']

        try:
            localPickupStart = datetime.datetime.strptime(store['pickup_interval']['start'],
                                                          '%Y-%m-%dT%H:%M:%S%z').replace(
                tzinfo=datetime.timezone.utc).astimezone(tz=None)
            localPickupEnd = datetime.datetime.strptime(store['pickup_interval']['end'], '%Y-%m-%dT%H:%M:%S%z').replace(
                tzinfo=datetime.timezone.utc).astimezone(tz=None)
            current_fav['pickup_start'] = maya.parse(
                localPickupStart).slang_date().capitalize() + " " + localPickupStart.strftime('%H:%M')
            current_fav['pickup_end'] = maya.parse(
                localPickupEnd).slang_date().capitalize() + " " + localPickupEnd.strftime('%H:%M')
        except KeyError:
            current_fav['pickup_start'] = None
            current_fav['pickup_end'] = None
        try:
            current_fav['rating'] = round(store['item']['average_overall_rating']['average_overall_rating'], 2)
        except KeyError:
            current_fav['rating'] = None

        new_api_result.append(current_fav)

    return new_api_result


def automatic_check():
    """
    Function that gets called via schedule every 3 minutes.
    Retrieves the data from TGTG API and selects the message to send.
    """

    # Get the global variable of items in stock
    global favourites_in_stock

    # Get all favorite items
    api_response = client.get_items()
    new_api_result = extract_api_result(api_response)

    list_of_item_ids = [fav['item_id'] for fav in new_api_result]
    for item_id in list_of_item_ids:
        try:
            old_stock = [item['items_available'] for item in favourites_in_stock if item['item_id'] == item_id][0]
            print(old_stock)
        except:
            old_stock = 0
            print(f"An exception occurred: The item_id was not known as a favorite before.")
        new_stock = [item['items_available'] for item in new_api_result if item['item_id'] == item_id][0]


        # Check, if the stock has changed. Send a message if so.
        if new_stock != old_stock:
            if old_stock == 0 and new_stock > 0:
                # Check if the stock was replenished, send an encouraging image message
                item_id2 = [item['item_id'] for item in new_api_result if item['item_id'] == item_id][0]
                display_name = [item['display_name'] for item in new_api_result if item['item_id'] == item_id][0]
                description = [item['description'] for item in new_api_result if item['item_id'] == item_id][0]
                price_including_tax = \
                    [item['price_including_taxes'] for item in new_api_result if item['item_id'] == item_id][0]
                rating = [item['rating'] for item in new_api_result if item['item_id'] == item_id][0]
                picup_start = [item['pickup_start'] for item in new_api_result if item['item_id'] == item_id][0]
                pickup_end = [item['pickup_end'] for item in new_api_result if item['item_id'] == item_id][0]
                address_line = [item['address_line'] for item in new_api_result if item['item_id'] == item_id][0]
                latitude = [item['latitude'] for item in new_api_result if item['item_id'] == item_id][0]
                longitude = [item['longitude'] for item in new_api_result if item['item_id'] == item_id][0]
                image = [item['category_picture'] for item in new_api_result if item['item_id'] == item_id][0]
                message = f"🥡 There are ***{new_stock}*** new goodie bags at [{display_name}](https://share.toogoodtogo.com/item/{item_id2})\n\n" \
                          f"📋 ___{description}___\n\n" \
                          f"💰 ***{price_including_tax}***\n" \
                          f"⭐ ***{rating}/5***\n" \
                          f"⏰ ***{picup_start} - {pickup_end}***\n" \
                          f"📍 [{address_line}](https://www.google.com/maps/search/?api=1&query={latitude}%2C{longitude})"
                telegram_bot_send_image(image, message)

            elif old_stock > new_stock == 0:
                display_name2 = [item['display_name'] for item in new_api_result if item['item_id'] == item_id][0]
                message = f" ❌ ***Sold out! There are no more goodie bags available at {display_name2}.***"
                telegram_bot_send_text(message)

            else:
                # Prepare a generic string, but with the important info
                display_name3 = [item['display_name'] for item in new_api_result if item['item_id'] == item_id][0]
                message = f"There was a change of number of goodie bags in stock from ***{old_stock}*** to ***{new_stock}*** at ***{display_name3}****"
                telegram_bot_send_text(message)
    # Reset the global information with the newest fetch
    favourites_in_stock = new_api_result

    # Print out some maintenance info in the terminal
    print(f"API run at {time.ctime(time.time())} successful. Current stock:")
    for item_id in list_of_item_ids:
        print(f"{[item['display_name'] for item in new_api_result if item['item_id'] == item_id][0]}:\
         {[item['items_available'] for item in new_api_result if item['item_id'] == item_id][0]}")


def still_alive():
    """
    This function gets called every 24 hours and sends a 'still alive' message to the admin.
    """

    global favourites_in_stock
    message = f"🤖 Current time: {time.ctime(time.time())}. The bot is still running.\n\n"
    telegram_bot_send_text(message)


# Use schedule to set up a recurrent checking
schedule.every(1).minutes.do(automatic_check)
schedule.every(24).hours.do(still_alive)

# Description of the service, that gets send once
telegram_bot_send_text(
    "The bot script has started successfully. The bot checks every 3 minutes, if there is something new at "
    "TooGoodToGo. "
    "Every 24 hours, the bots sends a 'still alive'-message.")

while True:
    schedule.run_pending()
    time.sleep(1)

