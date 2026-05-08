# YOLO-based Real-time AI Assistant Core

This is the core code of a real-time AI vision project implemented based on DXGI, TensorRT, and driver-level input.

---

### Core Idea

1. **Screenshot**: Use DXGI Desktop Duplication for low-latency screen capture.
2. **Inference**: Use ONNX Runtime + TensorRT backend to run end-to-end YOLO model.
3. **Input**: Call the `IbInputSimulator` library to simulate mouse movement through hardware drivers.

---

### **⚠️ Important Disclaimer**

* **99% of the code in this project is AI-assisted generated**, so all code is piled into `main.cpp`, the structure is messy, and comments may not be clear. This repository aims to share a feasible technical idea, not an engineered project.
* **Only the core code is uploaded**, all dependent environments (such as OpenCV, ONNX Runtime, CUDA, etc.) need to be **configured by the user themselves**.
* The `.onnx` model in the repository is only an example, you need to **train and replace it with your own model**.
* **This project is for learning and technical exchange only**, strictly prohibited for any illegal purposes. All consequences are borne by the user.

---

### **Dependencies & Credits**

This project can be realized thanks to the following excellent open-source projects:

* **[IbInputSimulator](https://github.com/Chaoses-Ib/IbInputSimulator)** by Chaoses-Ib: Used to implement driver-level mouse input simulation, which is the key to the entire project.

---

### **Running**

1. Configure all dependent environments yourself.
2. Put all files into a C++ project for compilation.
3. Ensure the `.onnx` model and `.dll` files are next to the `.exe`.
4. **Run with administrator privileges.**
