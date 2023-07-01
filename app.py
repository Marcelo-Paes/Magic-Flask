from flask import Flask, render_template, request
import requests
import json
import os

os.environ['EXCHANGERATE_API_KEY'] = 'sua_chave_de_api'
app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    card_name = request.form['card_name']
    response = requests.get(f'https://api.scryfall.com/cards/named?fuzzy={card_name}')
    card_data = json.loads(response.text)
    card_image = card_data['image_uris']['normal']
    card_description = card_data['oracle_text']
    card_price_usd = card_data['prices']['usd']
    card_price_brl = convert_to_brl(card_price_usd)
    return render_template('result.html', card_name=card_name, card_image=card_image, card_description=card_description, card_price_brl=card_price_brl)


@app.route('/result')
def result():
    card_name = request.args.get('card_name')
    response = requests.get(f'https://api.scryfall.com/cards/named?fuzzy={card_name}')
    card_data = json.loads(response.text)
    card_image = card_data['image_uris']['normal']
    card_description = card_data['oracle_text']
    card_price = card_data['prices']['usd']
    return render_template('result.html', card_name=card_name, card_image=card_image, card_description=card_description, card_price=card_price)

def convert_to_brl(price_usd):
    response = requests.get('https://api.bcb.gov.br/dados/serie/bcdata.sgs.10813/dados?formato=json')
    exchange_data = json.loads(response.text)
    exchange_rate = float(exchange_data[-1]['valor'])
    price_brl = round(float(price_usd) * exchange_rate, 2)
    return price_brl

@app.route('/add_deck', methods=['GET', 'POST'])
def add_deck():
    if request.method == 'POST':
        deck_name = request.form['deck_name']
        deck_list = request.form['deck_list']

        # Processar o arquivo de texto se fornecido
        if 'file_input' in request.files:
            file = request.files['file_input']
            if file.filename.endswith('.txt'):
                card_names = file.read().decode('utf-8').splitlines()
                card_names = [card.strip() for card in card_names if card.strip()]

        card_names = [card.strip() for card in card_names]  # Assume que as cartas estão separadas por linhas
        
        cards = []
        for card_name in card_names:
            response = requests.get(f'https://api.scryfall.com/cards/named?fuzzy={card_name.strip()}')
            card_data = json.loads(response.text)
            card_image = card_data.get('image_uris', {}).get('normal')
            if card_image:
                card_name = card_data.get('name')
                card_price_usd = card_data.get('prices', {}).get('usd')
                card_price_brl = convert_to_brl(card_price_usd)
                cards.append({'name': card_name, 'image': card_image, 'price_brl': card_price_brl})
        
        deck_formats = get_deck_formats(deck_list)
        return render_template('deck.html', deck_name=deck_name, deck_list=cards, deck_formats=deck_formats)
    
    return render_template('add_deck.html')


def get_deck_formats(deck_list):
    formats = ['Standard', 'Modern', 'Legacy', 'Vintage']  # Exemplo de formatos disponíveis
    return formats  # Substitua esta lógica com a verificação real do deck

if __name__ == '__main__':
    app.run()
