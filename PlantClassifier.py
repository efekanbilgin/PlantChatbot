import torch
import torch.nn as nn
import json
from PIL import Image
from torchvision.models import convnext_tiny
from torchvision import transforms

class PlantClassifier():

    def __init__(
            self,
            checkpoint_path: str = "best_model.pt",
            class_names_path: str = "class_names.json",
            img_size: int = 224,
            device: str | None = None,
    ):
        self.device = device or (
            torch.accelerator.current_accelerator().type
            if torch.accelerator.is_available()
            else "cpu"
        )
        self.img_size = img_size
        self.class_names = self._load_class_names(class_names_path)
        self.model = self._build_model(checkpoint_path, len(self.class_names))
        self.transform = self._build_transform()

    def _load_class_names(self, path: str) -> list[str]:
        with open(path, "r") as f:
            return json.load(f)

    def _build_model(self, checkpoint_path: str, num_classes: int):
        model = convnext_tiny(weights=None)
        in_features = model.classifier[2].in_features
        model.classifier[2] = nn.Linear(in_features, num_classes)

        state_dict = torch.load(checkpoint_path, map_location=self.device)
        model.load_state_dict(state_dict)

        model.to(self.device)
        model.eval()
        return model

    def _build_transform(self):
        return transforms.Compose([
            transforms.Resize(int(self.img_size * 1.14)),
            transforms.CenterCrop(self.img_size),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225],
            ),
        ])

    def predict(self, image_path: str, top_k: int = 3) -> list[dict]:
        image = Image.open(image_path).convert("RGB")
        input_tensor = self.transform(image).unsqueeze(0).to(self.device)

        with torch.no_grad():
            outputs = self.model(input_tensor)
            probs = torch.softmax(outputs, dim=1)[0]

        top_probs, top_indices = torch.topk(probs, top_k)

        return [
            {"species": self.class_names[idx.item()], "confidence": prob.item()}
            for prob, idx in zip(top_probs, top_indices)
        ]