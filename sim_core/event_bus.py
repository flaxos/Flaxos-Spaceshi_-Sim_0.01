from typing import Any, Callable, Dict, List
class EventBus:
    def __init__(self)->None:
        self._subs: Dict[str, List[Callable[[Any],None]]] = {}
    def subscribe(self, topic:str, fn:Callable[[Any],None]): self._subs.setdefault(topic, []).append(fn)
    def publish(self, topic:str, data:Any): 
        for fn in self._subs.get(topic, []):
            try: fn(data)
            except Exception: pass
