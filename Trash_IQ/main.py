from ultralytics import YOLO
import multiprocessing


def main():
	model = YOLO("yolov8m.pt")

	# use the model (ensure this runs under the main guard on Windows)
	results = model.train(data="data1.yaml", epochs=100, batch=-1, imgsz=640, workers=8, device=0)
	print("Training complete.")


if __name__ == "__main__":
	multiprocessing.freeze_support()
	main()
