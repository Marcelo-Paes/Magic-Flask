from flask import Flask, render_template, request,jsonify
import requests
import json
from cachetools import TTLCache
from concurrent.futures import ThreadPoolExecutor
import requests

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
        response = requests.get(f'https://api.scryfall.com/cards/autocomplete?q={card_name}')
        if response.status_code == 404:
            # Nenhum resultado encontrado para a busca parcial
            return render_template('error.html', message='Nenhum resultado encontrado para a busca parcial.')
        card_data = json.loads(response.text)
        if 'data' not in card_data or len(card_data['data']) == 0:
            # Nenhum resultado encontrado para a busca parcial
            return render_template('error.html', message='Nenhum resultado encontrado para a busca parcial.')
        card_name = card_data['data'][0]
        # Armazenar a resposta em cache
        cache[card_name] = card_data

    # Fazer uma nova requisição para obter os detalhes da carta
    response = requests.get(f'https://api.scryfall.com/cards/named?exact={card_name}')
    if response.status_code == 404:
        # Carta não encontrada na API
        return render_template('error.html', message='A carta não foi encontrada.')
    card_data = json.loads(response.text)

    card_image = ''
    card_image_front = ''
    card_image_back = ''
    card_price = 'N/A'

    # Verificar se a carta possui o atributo "image_uris" para cartas com uma face
    if 'image_uris' in card_data:
        card_image = card_data['image_uris'].get('normal')

    # Verificar se a carta possui o atributo "card_faces" para cartas com duas faces
    if 'card_faces' in card_data:
        card_faces = card_data['card_faces']
        if len(card_faces) == 2:
            card_price_front = card_faces[0].get('prices', {}).get('usd')
            card_price_back = card_faces[1].get('prices', {}).get('usd')
            card_image_front = card_faces[0].get('image_uris', {}).get('normal')
            card_image_back = card_faces[1].get('image_uris', {}).get('normal')

            if card_price_front is not None:
                card_price_front = convert_to_brl(float(card_price_front))
            if card_price_back is not None:
                card_price_back = convert_to_brl(float(card_price_back))

    # Obter o preço da carta
    card_price = card_data['prices'].get('usd')
    if card_price is not None:
        card_price = convert_to_brl(float(card_price))

    # Obter os formatos da carta
    card_formats = {}
    legalities = card_data.get('legalities', {})
    for format_name, legality in legalities.items():
        if legality == 'legal':
            card_formats[format_name] = legality

    # Verificar se é um terreno básico
    basic_land_names = ['Forest', 'Island', 'Mountain', 'Plains', 'Swamp']
    if card_name in basic_land_names:
        card_price = 'N/A'

    return render_template('result.html', card_name=card_name, card_price=card_price, card_image=card_image, card_image_front=card_image_front, card_image_back=card_image_back, card_formats=card_formats)
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

    card_image = ''
    if 'image_uris' in card_data:
        if 'normal' in card_data['image_uris']:
            card_image = card_data['image_uris']['normal']
        elif 'png' in card_data['image_uris']:
            card_image = card_data['image_uris']['png']

    card_description = card_data.get('oracle_text', '')
    card_price = card_data['prices'].get('usd', 'N/A')

    # Verificar se é um terreno básico
    basic_land_names = ['Forest', 'Island', 'Mountain', 'Plains', 'Swamp']
    if card_name in basic_land_names:
        card_price = 'N/A'

    return render_template('result.html', card_name=card_name, card_image=card_image, card_description=card_description, card_price=card_price)


def convert_to_brl(price_usd):
    response = requests.get('https://api.bcb.gov.br/dados/serie/bcdata.sgs.10813/dados?formato=json')
    exchange_data = json.loads(response.text)
    exchange_rate = float(exchange_data[-1]['valor'])
    if price_usd is None:
        price_brl = "N/A"  # Ou qualquer outro valor padrão desejado
    else:
        price_brl = round(float(price_usd) * exchange_rate, 2)
    return price_brl

def process_card(card_name):
    try:
        response = requests.get(f'https://api.scryfall.com/cards/named?exact={card_name.strip().replace(" ", "+")}')
        card_data = json.loads(response.text)
        card_image = card_data.get('image_uris', {}).get('normal')
        card_image_back = None
        card_price_usd = card_data.get('prices', {}).get('usd')
        card_price_brl = convert_to_brl(card_price_usd)

        if 'card_faces' in card_data:
            card_faces = card_data['card_faces']
            if len(card_faces) == 2:
                card_image_back = card_faces[1].get('image_uris', {}).get('normal')

        card_name = card_data.get('name')

        # Obter os formatos válidos da carta
        valid_formats = []
        legalities = card_data.get('legalities', {})
        for format_name, legality in legalities.items():
            if legality == 'legal':
                valid_formats.append(format_name)

        card = {
            'name': card_name,
            'image': card_image,
            'image_back': card_image_back,
            'price_brl': card_price_brl,
            'formats': valid_formats
        }

        return card
    except (requests.exceptions.RequestException, json.JSONDecodeError):
        return None



@app.route('/add_deck', methods=['GET', 'POST'])
def add_deck():
    deck_name = ''
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

        basic_land_names = ['Forest', 'Island', 'Mountain', 'Plains', 'Swamp']

        for card_name in card_names:
            # Verifica se há um número no início do nome da carta
            if card_name[0].isdigit():
                # Extrai o número e o nome da carta
                quantity, card_name = card_name.split(' ', 1)
                quantity = int(quantity)
            else:
                quantity = 1

            # Ignora os terrenos básicos
            if card_name in basic_land_names:
                continue

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
                    card['quantity'] = deck[card_name]  # Definindo a quantidade conforme a contagem no deck

                    # Atualiza a contagem de formatos
                    for format_name in card['formats']:
                        if format_name in format_counts:
                            format_counts[format_name] += 1

                    filtered_cards.append(card)

        # Renderização do template com as cartas e formato do deck
        return render_template('deck.html', deck_name=deck_name, deck_list=filtered_cards, format_counts=format_counts)

    return render_template('add_deck.html', deck_name=deck_name)


def process_card(card_name):
    try:
        response = requests.get(f'https://api.scryfall.com/cards/named?exact={card_name.strip().replace(" ", "+")}')
        card_data = json.loads(response.text)
        card_image = card_data.get('image_uris', {}).get('normal')
        card_image_back = None
        card_price_usd = card_data.get('prices', {}).get('usd')
        card_price_brl = convert_to_brl(card_price_usd)

        card_name = card_data.get('name')

        # Obter os formatos válidos da carta
        valid_formats = []
        legalities = card_data.get('legalities', {})
        for format_name, legality in legalities.items():
            if legality == 'legal':
                # Adicione a verificação para evitar formatos específicos
                if format_name not in ['gladiator', 'oathbreaker', 'duel','penny','predh','paupercommander','premodern']:
                    valid_formats.append(format_name)

        if 'card_faces' in card_data:
            card_faces = card_data['card_faces']
            if len(card_faces) == 2:
                card_image_back = card_faces[1].get('image_uris', {}).get('normal')

        card = {
            'name': card_name,
            'image': card_image,
            'image_back': card_image_back,
            'price_brl': card_price_brl,
            'formats': valid_formats
        }

        return card
    except (requests.exceptions.RequestException, json.JSONDecodeError):
        return None


def process_deck_list(deck_list):
    deck_cards = []
    basic_land_names = ['Forest', 'Island', 'Mountain', 'Plains', 'Swamp']
    for line in deck_list.splitlines():
        card_name, card_quantity = line.strip().split()
        if card_name not in basic_land_names:
            deck_cards.append((card_name, int(card_quantity)))
    return deck_cards
def get_card_info(card_name):
    try:
        response = requests.get(f'https://api.scryfall.com/cards/named?fuzzy={card_name}')
        if response.status_code == 200:
            card_data = response.json()
            print("Dados da carta:", card_data)  # Adicione esta linha para imprimir os dados obtidos
            return card_data
        else:
            print("Erro: Carta não encontrada")  # Adicione esta linha para imprimir um erro
            return None  # Carta não encontrada
    except requests.exceptions.RequestException:
        print("Erro na solicitação")  # Adicione esta linha para imprimir um erro
        return None  # Erro na solicitação
@app.route('/card_format/<card_name>', methods=['GET'])
def card_format(card_name):
    print(f'Servidor Flask: Rota chamada para a carta {card_name}')
    card_info = get_card_info(card_name)
    
    if card_info is not None:
        # Verifique se a carta tem informações sobre formatos
        if 'legalities' in card_info:
            format_info = card_info['legalities']
            # Supondo que você queira o formato "standard", mas você pode personalizar conforme necessário
            format_name = format_info.get('standard', 'N/A')
            return jsonify({'formatInfo': {'format': format_name}})
        else:
            return jsonify({'formatInfo': 'Informações de formato não disponíveis para esta carta.'})
    else:
        return jsonify({'formatInfo': 'Carta não encontrada.'})
    
if __name__ == '__main__':
    app.run()