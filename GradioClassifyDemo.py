import gradio as gr
from Agent import PlantChatbot

bot = PlantChatbot()


def handle_image(image_path):
    if image_path is None:
        return "Bitki görseli yükleyin."

    result = bot.classify_image(image_path, top_k=3)

    lines = [
        f"**Tahmin:** {result['predicted_species']} (%{result['confidence']*100:.2f})",
        "",
        "**Diğer olasılıklar:**",
    ]
    for item in result["top_k"]:
        lines.append(f"- {item['species']}: %{item['confidence']*100:.2f}")

    return "\n".join(lines)


with gr.Blocks() as demo:
    gr.Markdown("## Bitki Sınıflandırma")
    image_input = gr.Image(type="filepath", label="Bitki görseli yükle")
    output = gr.Markdown()
    submit_btn = gr.Button("Analiz Et")

    submit_btn.click(fn=handle_image, inputs=image_input, outputs=output)


if __name__ == "__main__":
    demo.launch()