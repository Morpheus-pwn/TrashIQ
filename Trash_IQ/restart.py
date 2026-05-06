from ultralytics import YOLO
import multiprocessing

def main():
    model = YOLO("C:/Users/pawan/runs/detect/train8/weights/last.pt")
    model.train(resume=True, epochs=100, batch=-1, imgsz=640, workers=8, device=0)

if __name__ == "__main__":
	multiprocessing.freeze_support()
	main()