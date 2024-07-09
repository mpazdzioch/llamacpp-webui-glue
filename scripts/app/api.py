from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/api/llamacpp/new', methods=['POST'])
def new_llama():
    # simulate creating a new llama
    llama_id = 42
    return jsonify({'message': 'New llama created!', 'id': llama_id})

if __name__ == '__main__':
    app.run(debug=True, port=80, host='0.0.0.0')  # Listen on port 8080