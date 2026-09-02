from PlantClassifier import PlantClassifier


class PlantChatbot:

    def __init__(
        self,
        checkpoint_path: str = "best_model.pt",
        class_names_path: str = "class_names.json",
    ):
        self.classifier = PlantClassifier(
            checkpoint_path=checkpoint_path,
            class_names_path=class_names_path,
        )

    def classify_image(self, image_path: str, top_k: int = 3) -> dict:

        results = self.classifier.predict(image_path, top_k=top_k)
        top_result = results[0]

        return {
            "predicted_species": top_result["species"],
            "confidence": top_result["confidence"],
            "top_k": results,
        }


if __name__ == "__main__":
    #manuel test
    bot = PlantChatbot()
    image_path = input("Image path: ").strip()
    result = bot.classify_image(image_path)

    print(f"\nTahmin: {result['predicted_species']} (%{result['confidence']*100:.2f})")
    print("Diğer olasılıklar:")
    for item in result["top_k"]:
        print(f"  - {item['species']:40s} %{item['confidence']*100:.2f}")