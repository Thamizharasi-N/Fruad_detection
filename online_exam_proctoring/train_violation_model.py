"""
train_violation_model.py
========================
Standalone script to train a CNN model for exam violation detection.

This file is completely independent — it does NOT modify or interact with
any existing project views, models, or configurations.

Expected dataset structure:
    media/datasets/violations/
    ├── normal/
    ├── multiple_face/
    ├── face_not_visible/
    ├── book_visible/
    └── looking_away/

Each sub-folder must contain images belonging to that class.

Usage:
    Run this script from the 'online_exam_proctoring' directory:
        python train_violation_model.py

Output:
    Trained model saved to: models/violation_detector.h5
"""

import os
import sys
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime

# ---------------------------------------------------------------------------
# 1. Imports — TensorFlow / Keras
# ---------------------------------------------------------------------------
try:
    import tensorflow as tf
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import (
        Conv2D, MaxPooling2D, Flatten,
        Dense, Dropout, BatchNormalization
    )
    from tensorflow.keras.preprocessing.image import ImageDataGenerator
    from tensorflow.keras.callbacks import (
        ModelCheckpoint, EarlyStopping, ReduceLROnPlateau
    )
    from tensorflow.keras.optimizers import Adam
    print(f"[INFO] TensorFlow version: {tf.__version__}")
except ImportError:
    print("[ERROR] TensorFlow is not installed.")
    print("        Install it with:  pip install tensorflow")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 2. Configuration — paths, image size, training hyper-parameters
# ---------------------------------------------------------------------------

# Path to the violations dataset folder (relative to this script's location)
DATASET_PATH = "media/datasets/violations"

# Where to save the trained model
MODEL_SAVE_DIR  = "models"
MODEL_SAVE_PATH = os.path.join(MODEL_SAVE_DIR, "violation_detector.h5")

# Image dimensions expected by the CNN
IMAGE_SIZE   = (224, 224)        # height x width
IMAGE_SHAPE  = (224, 224, 3)     # channels = 3 (RGB)

# Training settings
BATCH_SIZE        = 32
EPOCHS            = 30           # max epochs (early-stopping may stop earlier)
VALIDATION_SPLIT  = 0.20         # 20 % of data used for validation
LEARNING_RATE     = 1e-4
SEED              = 42

# The 5 violation classes (folder names must match exactly)
CLASS_NAMES = [
    "normal",
    "multiple_face",
    "face_not_visible",
    "book_visible",
    "looking_away",
]
NUM_CLASSES = len(CLASS_NAMES)

# ---------------------------------------------------------------------------
# 3. Pre-flight checks
# ---------------------------------------------------------------------------

def validate_dataset(dataset_path: str) -> None:
    """
    Verify that the dataset directory exists and contains at least
    the expected class sub-folders with at least one image each.
    """
    if not os.path.isdir(dataset_path):
        print(f"[ERROR] Dataset path not found: '{dataset_path}'")
        print("        Make sure you are running this script from the")
        print("        'online_exam_proctoring' directory and the dataset")
        print("        folders have been created.")
        sys.exit(1)

    print(f"\n[INFO] Dataset path  : {os.path.abspath(dataset_path)}")
    print(f"[INFO] Classes expected: {CLASS_NAMES}\n")

    missing_classes = []
    empty_classes   = []

    for cls in CLASS_NAMES:
        cls_dir = os.path.join(dataset_path, cls)
        if not os.path.isdir(cls_dir):
            missing_classes.append(cls)
        else:
            # Count image files inside
            images = [
                f for f in os.listdir(cls_dir)
                if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".webp"))
            ]
            count = len(images)
            print(f"  [{cls:20s}]  {count:>5d} image(s)")
            if count == 0:
                empty_classes.append(cls)

    if missing_classes:
        print(f"\n[WARNING] Missing class folder(s): {missing_classes}")
        print("          Create the folders and add images before training.")

    if empty_classes:
        print(f"\n[WARNING] Empty class folder(s): {empty_classes}")
        print("          Add images to these folders before training.")

    if missing_classes or empty_classes:
        print("\n[ERROR] Cannot train — dataset is incomplete. Exiting.")
        sys.exit(1)

    print("\n[INFO] Dataset validation passed.\n")


def ensure_model_dir(model_dir: str) -> None:
    """Create the models/ directory if it does not already exist."""
    os.makedirs(model_dir, exist_ok=True)
    print(f"[INFO] Model will be saved to: {os.path.abspath(MODEL_SAVE_PATH)}")


# ---------------------------------------------------------------------------
# 4. Data generators — augmentation for training, rescale-only for validation
# ---------------------------------------------------------------------------

def build_data_generators(dataset_path: str):
    """
    Create Keras ImageDataGenerators for training and validation.

    Training generator applies random augmentations to improve generalisation.
    Validation generator only rescales pixel values to [0, 1].
    """

    # --- Training augmentation ---
    train_datagen = ImageDataGenerator(
        rescale=1.0 / 255,           # normalise pixel values to [0, 1]
        validation_split=VALIDATION_SPLIT,

        # Spatial augmentations
        rotation_range=20,           # randomly rotate images ±20°
        width_shift_range=0.15,      # horizontal shift up to 15 %
        height_shift_range=0.15,     # vertical shift up to 15 %
        zoom_range=0.15,             # random zoom in/out
        horizontal_flip=True,        # randomly mirror images

        # Pixel-level augmentations
        brightness_range=[0.7, 1.3], # random brightness adjustment
        fill_mode="nearest",         # fill empty pixels after transform
    )

    # --- Validation (no augmentation, only normalisation) ---
    val_datagen = ImageDataGenerator(
        rescale=1.0 / 255,
        validation_split=VALIDATION_SPLIT,
    )

    # --- Training generator ---
    train_generator = train_datagen.flow_from_directory(
        dataset_path,
        target_size=IMAGE_SIZE,      # resize every image to 224×224
        batch_size=BATCH_SIZE,
        class_mode="categorical",    # one-hot encoded labels for 5 classes
        subset="training",
        seed=SEED,
        shuffle=True,
        classes=CLASS_NAMES,         # enforce a consistent class index order
    )

    # --- Validation generator ---
    val_generator = val_datagen.flow_from_directory(
        dataset_path,
        target_size=IMAGE_SIZE,
        batch_size=BATCH_SIZE,
        class_mode="categorical",
        subset="validation",
        seed=SEED,
        shuffle=False,
        classes=CLASS_NAMES,
    )

    print(f"\n[INFO] Training samples   : {train_generator.samples}")
    print(f"[INFO] Validation samples : {val_generator.samples}")
    print(f"[INFO] Class indices      : {train_generator.class_indices}\n")

    return train_generator, val_generator


# ---------------------------------------------------------------------------
# 5. CNN model architecture
# ---------------------------------------------------------------------------

def build_cnn_model(input_shape: tuple, num_classes: int) -> Sequential:
    """
    Build and compile a CNN model suitable for 5-class image classification.

    Architecture overview:
        Block 1  →  Conv(32)  → BN → Pool
        Block 2  →  Conv(64)  → BN → Pool
        Block 3  →  Conv(128) → BN → Pool
        Block 4  →  Conv(256) → BN → Pool
        Head     →  Flatten → Dense(512) → Dropout → Dense(num_classes, softmax)
    """

    model = Sequential(name="ViolationDetectorCNN")

    # ------------------------------------------------------------------
    # Block 1 — extract low-level features (edges, textures)
    # ------------------------------------------------------------------
    model.add(Conv2D(32, (3, 3), activation="relu",
                     padding="same", input_shape=input_shape))
    model.add(BatchNormalization())         # stabilise & speed up training
    model.add(Conv2D(32, (3, 3), activation="relu", padding="same"))
    model.add(BatchNormalization())
    model.add(MaxPooling2D(pool_size=(2, 2)))  # 224 → 112
    model.add(Dropout(0.25))

    # ------------------------------------------------------------------
    # Block 2 — mid-level features (shapes, patterns)
    # ------------------------------------------------------------------
    model.add(Conv2D(64, (3, 3), activation="relu", padding="same"))
    model.add(BatchNormalization())
    model.add(Conv2D(64, (3, 3), activation="relu", padding="same"))
    model.add(BatchNormalization())
    model.add(MaxPooling2D(pool_size=(2, 2)))  # 112 → 56
    model.add(Dropout(0.25))

    # ------------------------------------------------------------------
    # Block 3 — higher-level features
    # ------------------------------------------------------------------
    model.add(Conv2D(128, (3, 3), activation="relu", padding="same"))
    model.add(BatchNormalization())
    model.add(Conv2D(128, (3, 3), activation="relu", padding="same"))
    model.add(BatchNormalization())
    model.add(MaxPooling2D(pool_size=(2, 2)))  # 56 → 28
    model.add(Dropout(0.30))

    # ------------------------------------------------------------------
    # Block 4 — complex, semantic features
    # ------------------------------------------------------------------
    model.add(Conv2D(256, (3, 3), activation="relu", padding="same"))
    model.add(BatchNormalization())
    model.add(Conv2D(256, (3, 3), activation="relu", padding="same"))
    model.add(BatchNormalization())
    model.add(MaxPooling2D(pool_size=(2, 2)))  # 28 → 14
    model.add(Dropout(0.30))

    # ------------------------------------------------------------------
    # Classification head
    # ------------------------------------------------------------------
    model.add(Flatten())                        # 14×14×256 → 50176
    model.add(Dense(512, activation="relu"))    # fully-connected layer
    model.add(BatchNormalization())
    model.add(Dropout(0.50))                    # strong dropout before output
    model.add(Dense(num_classes, activation="softmax"))  # 5-class probabilities

    # ------------------------------------------------------------------
    # Compile — categorical cross-entropy for multi-class classification
    # ------------------------------------------------------------------
    model.compile(
        optimizer=Adam(learning_rate=LEARNING_RATE),
        loss="categorical_crossentropy",
        metrics=["accuracy"],
    )

    return model


# ---------------------------------------------------------------------------
# 6. Training callbacks
# ---------------------------------------------------------------------------

def get_callbacks(model_save_path: str) -> list:
    """
    Return a list of Keras callbacks used during training:
      - ModelCheckpoint  : save the best model (by val_accuracy)
      - EarlyStopping    : stop training if val_loss stops improving
      - ReduceLROnPlateau: lower the learning rate when plateauing
    """

    checkpoint = ModelCheckpoint(
        filepath=model_save_path,
        monitor="val_accuracy",    # track validation accuracy
        save_best_only=True,       # only overwrite when improved
        verbose=1,
        mode="max",
    )

    early_stop = EarlyStopping(
        monitor="val_loss",
        patience=7,                # stop after 7 epochs of no improvement
        restore_best_weights=True, # revert to the best weights at the end
        verbose=1,
    )

    reduce_lr = ReduceLROnPlateau(
        monitor="val_loss",
        factor=0.5,                # halve the learning rate
        patience=3,                # after 3 epochs of no improvement
        min_lr=1e-7,
        verbose=1,
    )

    return [checkpoint, early_stop, reduce_lr]


# ---------------------------------------------------------------------------
# 7. Training loop
# ---------------------------------------------------------------------------

def train_model(model, train_gen, val_gen, epochs: int, callbacks: list):
    """
    Fit the CNN model on the training generator and evaluate on the
    validation generator.  Returns the Keras History object.
    """

    print("\n" + "=" * 60)
    print("  STARTING TRAINING")
    print(f"  Epochs       : {epochs}")
    print(f"  Batch size   : {BATCH_SIZE}")
    print(f"  Learning rate: {LEARNING_RATE}")
    print(f"  Image size   : {IMAGE_SIZE}")
    print("=" * 60 + "\n")

    history = model.fit(
        train_gen,
        validation_data=val_gen,
        epochs=epochs,
        callbacks=callbacks,
        verbose=1,                 # print one line of metrics per epoch
    )

    return history


# ---------------------------------------------------------------------------
# 8. Results reporting
# ---------------------------------------------------------------------------

def print_training_summary(history) -> None:
    """
    Print a concise summary of training and validation accuracy/loss
    for every epoch, and highlight the best epoch.
    """

    train_acc  = history.history["accuracy"]
    val_acc    = history.history["val_accuracy"]
    train_loss = history.history["loss"]
    val_loss   = history.history["val_loss"]

    best_epoch    = int(np.argmax(val_acc))       # epoch with highest val_acc
    best_val_acc  = val_acc[best_epoch]
    best_val_loss = val_loss[best_epoch]

    print("\n" + "=" * 60)
    print("  TRAINING SUMMARY  (per epoch)")
    print("=" * 60)
    print(f"  {'Epoch':>6}  {'Train Acc':>10}  {'Val Acc':>10}  "
          f"{'Train Loss':>12}  {'Val Loss':>10}")
    print("-" * 60)

    for epoch_idx, (ta, va, tl, vl) in enumerate(
            zip(train_acc, val_acc, train_loss, val_loss), start=1):
        marker = " ◄ BEST" if (epoch_idx - 1) == best_epoch else ""
        print(f"  {epoch_idx:>6}  {ta:>10.4f}  {va:>10.4f}  "
              f"{tl:>12.6f}  {vl:>10.6f}{marker}")

    print("-" * 60)
    print(f"\n  Best epoch      : {best_epoch + 1}")
    print(f"  Best val_acc    : {best_val_acc:.4f}  ({best_val_acc*100:.2f} %)")
    print(f"  Best val_loss   : {best_val_loss:.6f}")
    print("=" * 60 + "\n")


def save_training_plots(history, save_dir: str) -> None:
    """
    Save accuracy and loss plots as PNG files inside 'save_dir'.
    These are optional — training will succeed even if matplotlib fails.
    """
    try:
        os.makedirs(save_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Accuracy plot
        axes[0].plot(history.history["accuracy"],    label="Train Accuracy")
        axes[0].plot(history.history["val_accuracy"], label="Val Accuracy")
        axes[0].set_title("Model Accuracy per Epoch")
        axes[0].set_xlabel("Epoch")
        axes[0].set_ylabel("Accuracy")
        axes[0].legend()
        axes[0].grid(True)

        # Loss plot
        axes[1].plot(history.history["loss"],     label="Train Loss")
        axes[1].plot(history.history["val_loss"], label="Val Loss")
        axes[1].set_title("Model Loss per Epoch")
        axes[1].set_xlabel("Epoch")
        axes[1].set_ylabel("Loss")
        axes[1].legend()
        axes[1].grid(True)

        plot_path = os.path.join(save_dir, f"training_plot_{timestamp}.png")
        plt.tight_layout()
        plt.savefig(plot_path)
        plt.close()
        print(f"[INFO] Training plots saved to: {plot_path}")
    except Exception as exc:
        print(f"[WARNING] Could not save training plots: {exc}")


# ---------------------------------------------------------------------------
# 9. Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    print("\n" + "=" * 60)
    print("  VIOLATION DETECTOR — CNN TRAINING SCRIPT")
    print("=" * 60)
    print(f"  Script started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # ── Step 1: validate that the dataset folders exist ──────────────────
    validate_dataset(DATASET_PATH)

    # ── Step 2: create 'models/' output directory ─────────────────────────
    ensure_model_dir(MODEL_SAVE_DIR)

    # ── Step 3: build Keras data generators ───────────────────────────────
    train_gen, val_gen = build_data_generators(DATASET_PATH)

    # ── Step 4: build the CNN model and print its architecture ────────────
    model = build_cnn_model(input_shape=IMAGE_SHAPE, num_classes=NUM_CLASSES)
    model.summary()

    # ── Step 5: define callbacks ──────────────────────────────────────────
    callbacks = get_callbacks(MODEL_SAVE_PATH)

    # ── Step 6: train the model ───────────────────────────────────────────
    history = train_model(model, train_gen, val_gen,
                          epochs=EPOCHS, callbacks=callbacks)

    # ── Step 7: print per-epoch accuracy / loss summary ───────────────────
    print_training_summary(history)

    # ── Step 8: save accuracy / loss plots ────────────────────────────────
    save_training_plots(history, save_dir=MODEL_SAVE_DIR)

    # ── Step 9: final confirmation ────────────────────────────────────────
    if os.path.isfile(MODEL_SAVE_PATH):
        size_mb = os.path.getsize(MODEL_SAVE_PATH) / (1024 * 1024)
        print(f"[SUCCESS] Model saved : {os.path.abspath(MODEL_SAVE_PATH)}")
        print(f"          File size   : {size_mb:.2f} MB")
    else:
        print("[WARNING] Model file not found — training may have failed.")

    print(f"\n  Script finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")
