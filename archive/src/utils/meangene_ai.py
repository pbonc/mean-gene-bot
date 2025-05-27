import openai

class MeanGeneAI:
    def __init__(self, api_key, persona=None):
        openai.api_key = api_key
        self.persona = persona or (
            "You are MeanGeneBot, a boisterous, energetic wrestling announcer. "
            "You make every event sound epic, use wrestling catchphrases, and add hype."
        )

    def generate_message(self, context, temperature=0.85, max_tokens=100):
        prompt = f"{self.persona}\n\nEvent: {context}\n\nRespond as MeanGeneBot:"
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": self.persona},
                {"role": "user", "content": f"{context}\nMake it sound legendary!"},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()