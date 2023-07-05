from flask import Flask, render_template, request
import requests
import json
import os
from cachetools import TTLCache
from concurrent.futures import ThreadPoolExecutor
from math import ceil
os.environ['EXCHANGERATE_API_KEY'] = 'sua_chave_de_api'
app = Flask(__name__)

# Cache com tempo de vida de 1 hora (3600 segundos)
cache = TTLCache(maxsize=1000, ttl=3600)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    card_name = request.form['card_name']

    # Verificar se a resposta está em cache
    if card_name in cache:
        card_data = cache[card_name]
    else:
        response = requests.get(f'https://api.scryfall.com/cards/named?fuzzy={card_name}')
        if response.status_code == 404:
            # Carta não encontrada na API
            return render_template('error.html', message='A carta não foi encontrada.')
        card_data = json.loads(response.text)
        # Armazenar a resposta em cache
        cache[card_name] = card_data

    # Verificar se há múltiplas cartas com o mesmo nome
    if 'data' in card_data and len(card_data['data']) > 1:
        # Pegar apenas a primeira carta encontrada
        card_data = card_data['data'][0]

    card_image = card_data['image_uris']['normal']
    card_description = card_data['oracle_text']
    card_price_usd = card_data['prices']['usd']

    # Verificar se o preço em USD é None e atribuir 'N/A' como valor padrão
    if card_price_usd is None:
        card_price_usd = 'N/A'
        card_price_brl = 'N/A'
    else:
        card_price_brl = convert_to_brl(float(card_price_usd))

    # Obter os formatos da carta
    card_formats = {}
    legalities = card_data.get('legalities', {})
    for format_name, legality in legalities.items():
        if legality == 'legal':
            card_formats[format_name] = legality

    # Verificar se é um terreno básico
    basic_land_names = ['Forest', 'Island', 'Mountain', 'Plains', 'Swamp']
    if card_name in basic_land_names:
        card_price_usd = 'N/A'
        card_price_brl = 'N/A'
        response = requests.get(f'https://api.scryfall.com/cards/named?exact={card_name}')
        if response.status_code == 404:
            # Carta básica não encontrada na API
            return render_template('error.html', message='A carta básica não foi encontrada.')
        card_data = json.loads(response.text)
        card_image = card_data['image_uris']['normal']

    return render_template('result.html', card_name=card_name, card_image=card_image, card_description=card_description, card_price_usd=card_price_usd, card_price_brl=card_price_brl, card_formats=card_formats)


# Rota de erro
@app.route('/error')
def error():
    card_name = request.args.get('card_name')
    return render_template('error.html', card_name=card_name)

@app.route('/result')
def result():
    card_name = request.args.get('card_name')
    response = requests.get(f'https://api.scryfall.com/cards/named?exact={card_name.strip().replace(" ", "+")}')
    card_data = json.loads(response.text)
    card_image = card_data['image_uris']['normal']
    card_description = card_data['oracle_text']
    card_price = card_data['prices']['usd']

    # Verificar se é um terreno básico
    basic_land_names = ['Forest', 'Island', 'Mountain', 'Plains', 'Swamp']
    if card_name in basic_land_names:
        card_price = 'N/A'

    return render_template('result.html', card_name=card_name, card_image=card_image, card_description=card_description, card_price=card_price)

def convert_to_brl(price_usd):
    response = requests.get('https://api.bcb.gov.br/dados/serie/bcdata.sgs.10813/dados?formato=json')
    exchange_data = json.loads(response.text)
    exchange_rate = float(exchange_data[-1]['valor'])
    price_brl = round(float(price_usd) * exchange_rate, 2)
    return price_brl

def process_card(card_name):
    try:
        response = requests.get(f'https://api.scryfall.com/cards/named?exact={card_name.strip().replace(" ", "+")}')
        card_data = json.loads(response.text)
        card_image = card_data.get('image_uris', {}).get('normal')
        if card_image:
            card_name = card_data.get('name')
            card_price_usd = card_data.get('prices', {}).get('usd')
            card_price_brl = convert_to_brl(card_price_usd)
            return {'name': card_name, 'image': card_image, 'price_brl': card_price_brl}
        else:
            return None
    except (requests.exceptions.RequestException, json.JSONDecodeError):
        return None

@app.route('/add_deck', methods=['GET', 'POST'])
def add_deck():
    if request.method == 'POST':
        deck_name = request.form['deck_name']
        deck_list = request.form['deck_list']

        card_names = [card.strip() for card in deck_list.split('\n') if card.strip()]  # Assume que as cartas estão separadas por linhas

        deck = {}
        format_counts = {
            'standard': 0,
            'modern': 0,
            'legacy': 0,
            'vintage': 0,
            'commander': 0,
            'pauper': 0,
            'pioneer': 0,
            'historic': 0
        }

        for card_name in card_names:
            # Verifica se há um número no início do nome da carta
            if card_name[0].isdigit():
                # Extrai o número e o nome da carta
                quantity, card_name = card_name.split(' ', 1)
                quantity = int(quantity)
            else:
                quantity = 1

            # Atualiza a quantidade correspondente da carta no deck
            if card_name in deck:
                deck[card_name] += quantity
            else:
                deck[card_name] = quantity

        cards = []
        card_requests = list(deck.keys())

        # Função para processar a carta em paralelo
        def process_card_parallel(card_name):
            return process_card(card_name)

        # Processamento paralelo das cartas
        with ThreadPoolExecutor() as executor:
            # Executa o processamento das cartas em paralelo e obtém os resultados
            cards = list(executor.map(process_card_parallel, card_requests))

        # Filtra as cartas que não foram encontradas e atualiza a quantidade no deck
        filtered_cards = []

        for card in cards:
            if card is not None:
                card_name = card['name']
                if card_name in deck:
                    card['quantity'] = 1  # Definindo a quantidade como 1 para cada carta encontrada

                    # Atualiza a contagem de formatos
                    for format_name in card['formats']:
                        if format_name in format_counts:
                            format_counts[format_name] += 1

                    filtered_cards.append(card)

        # Renderização do template com as cartas e formato do deck
        return render_template('deck.html', deck_name=deck_name, deck_list=filtered_cards, format_counts=format_counts)

    return render_template('add_deck.html')

def process_card(card_name):
    try:
        response = requests.get(f'https://api.scryfall.com/cards/named?exact={card_name.strip().replace(" ", "+")}')
        card_data = json.loads(response.text)
        card_image = card_data.get('image_uris', {}).get('normal')
        if card_image:
            card_name = card_data.get('name')
            card_price_usd = card_data.get('prices', {}).get('usd')
            card_price_brl = convert_to_brl(card_price_usd)

            # Obter os formatos válidos da carta
            valid_formats = []
            legalities = card_data.get('legalities', {})
            for format_name, legality in legalities.items():
                if legality == 'legal':
                    valid_formats.append(format_name)

            #print("Formatos válidos da carta:", valid_formats)

            return {'name': card_name, 'image': card_image, 'price_brl': card_price_brl, 'formats': valid_formats}
        else:
            return None
    except (requests.exceptions.RequestException, json.JSONDecodeError):
        return None


    


if __name__ == '__main__':
    app.run()