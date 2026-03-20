"""
neural_swarm.py — GPU-роутер Аргоса (RX 580 / RX 560).

Распределяет задачи между «Мозгом» (RX 580, 8 ГБ) и «Рефлексами» (RX 560, 4 ГБ),
чтобы система не зависала и VRAM каждой карты использовалась эффективно.
"""
from __future__ import annotations

import os
from typing import Any, TYPE_CHECKING

from src.argos_logger import get_logger

if TYPE_CHECKING:
    pass

log = get_logger("argos.neural_swarm")

# Соответствие индексов GPU именам карт (настраивается через env)
_GPU_BRAIN  = os.getenv("NEURAL_SWARM_BRAIN_GPU",   "0")   # RX 580 8GB — основной мозг
_GPU_REFLEX = os.getenv("NEURAL_SWARM_REFLEX_GPU",  "1")   # RX 560 4GB — рефлексы/GUI

# Задачи, требующие «тяжёлого» GPU (RX 580)
_HEAVY_TASK_TYPES = frozenset({
    "code_gen",
    "deep_analysis",
    "shodan_scan",
    "evolution",
    "llm_inference",
    "embedding",
})


class NeuralSwarm:
    """
    Управляет распределением нагрузки между RX 580 (8GB) и RX 560 (4GB).

    • RX 580 (heavy):  Llama-3.1-8B, генерация кода, глубокий анализ.
    • RX 560 (light):  Vision, голос, сенсоры, GUI, мелкие задачи.
    """

    def __init__(self, core=None):
        self.core = core
        self.gpu_map = {
            "heavy": _GPU_BRAIN,
            "light": _GPU_REFLEX,
        }

    # ── МАРШРУТИЗАЦИЯ ────────────────────────────────────────────────────────

    def route_task(self, task_type: str, payload: Any = None) -> Any:
        """
        Направляет задачу на нужный GPU.

        :param task_type: Тип задачи (напр. "code_gen", "vision", "voice").
        :param payload:   Данные для обработки.
        :returns:         Результат выполнения задачи.
        """
        gpu_tier = "heavy" if task_type in _HEAVY_TASK_TYPES else "light"
        gpu_id   = self.gpu_map[gpu_tier]
        label    = "🧠 RX 580 (мозг)" if gpu_tier == "heavy" else "⚡ RX 560 (рефлексы)"
        log.info("[NeuralSwarm] %s → %s (GPU:%s)", task_type, label, gpu_id)
        return self._execute_on_gpu(gpu_id, task_type, payload)

    def _execute_on_gpu(self, gpu_id: str, task_type: str, payload: Any) -> Any:
        """
        Выполняет задачу с указанием конкретного GPU через переменные окружения.

        Устанавливает HIP_VISIBLE_DEVICES (AMD ROCm) и CUDA_VISIBLE_DEVICES (NVIDIA/обёртки),
        затем делегирует задачу AI-провайдеру ядра.
        """
        # Задаём переменные окружения для GPU-изоляции
        env_backup_hip  = os.environ.get("HIP_VISIBLE_DEVICES")
        env_backup_cuda = os.environ.get("CUDA_VISIBLE_DEVICES")

        try:
            os.environ["HIP_VISIBLE_DEVICES"]  = gpu_id
            os.environ["CUDA_VISIBLE_DEVICES"] = gpu_id

            if self.core:
                return self._dispatch_to_core(task_type, payload)
            log.debug("[NeuralSwarm] core недоступен — задача %s не выполнена", task_type)
            return None
        finally:
            # Восстанавливаем исходные значения
            if env_backup_hip is not None:
                os.environ["HIP_VISIBLE_DEVICES"] = env_backup_hip
            else:
                os.environ.pop("HIP_VISIBLE_DEVICES", None)

            if env_backup_cuda is not None:
                os.environ["CUDA_VISIBLE_DEVICES"] = env_backup_cuda
            else:
                os.environ.pop("CUDA_VISIBLE_DEVICES", None)

    def _dispatch_to_core(self, task_type: str, payload: Any) -> Any:
        """Делегирует задачу соответствующему методу core."""
        if task_type in ("code_gen", "deep_analysis", "llm_inference", "evolution"):
            if hasattr(self.core, "_ask_ollama"):
                prompt = payload if isinstance(payload, str) else str(payload)
                return self.core._ask_ollama("", prompt)

        if task_type == "vision" and hasattr(self.core, "vision"):
            if callable(getattr(self.core.vision, "analyse_image", None)):
                return self.core.vision.analyse_image(payload)

        # Общий путь: ask через execute_intent
        if hasattr(self.core, "execute_intent"):
            text = payload if isinstance(payload, str) else str(payload)
            return self.core.execute_intent(text, None, None)

        return None

    def get_dispatch_env(self, task_type: str) -> dict:
        """
        Возвращает копию os.environ с выставленными HIP/CUDA_VISIBLE_DEVICES
        для заданного типа задачи.

        :param task_type: Тип задачи (напр. "code_gen", "vision").
        :returns:         Словарь переменных окружения для нужного GPU.
        """
        gpu_tier = "heavy" if task_type in _HEAVY_TASK_TYPES else "light"
        gpu_id   = self.gpu_map[gpu_tier]
        label    = "🧠 RX 580 (мозг)" if gpu_tier == "heavy" else "⚡ RX 560 (рефлексы)"
        log.info("[NeuralSwarm] get_dispatch_env: '%s' → %s (GPU:%s)", task_type, label, gpu_id)
        env = os.environ.copy()
        env["HIP_VISIBLE_DEVICES"]  = gpu_id
        env["CUDA_VISIBLE_DEVICES"] = gpu_id
        return env

    # ── СТАТУС ───────────────────────────────────────────────────────────────

    def status(self) -> str:
        """Возвращает текущую конфигурацию GPU-роутера."""
        return (
            f"🧠 NeuralSwarm GPU Router:\n"
            f"  Heavy (RX 580): GPU index {self.gpu_map['heavy']}\n"
            f"  Light (RX 560): GPU index {self.gpu_map['light']}\n"
            f"  Heavy tasks: {', '.join(sorted(_HEAVY_TASK_TYPES))}"
        )
