class WidgetUpdater:
    """
    Controla los elementos visuales del Widget en OBS a través de WebSocket.
    Permite cambiar textos dinámicamente.
    """
    def __init__(self, obs_controller, text_source_name: str):
        self.obs = obs_controller
        self.text_source_name = text_source_name

    def update_song_info(self, album: str, track: str) -> None:
        """Actualiza el texto en OBS usando el componente de Texto GDI/FreeType2."""
        if not self.obs.connected:
            return
            
        try:
            text_content = f"{album}\nTrack: {track}"
            self.obs.set_input_settings(
                input_name=self.text_source_name,
                settings={
                    "text": text_content,
                    "align": "center",
                    # Resetear forzosamente las cajas delimitadoras
                    "extents": False,
                    "extents_wrap": False,
                    "extents_cx": 0,
                    "extents_cy": 0,
                    "word_wrap": False,
                    "custom_width": 0
                }
            )
        except Exception:
            pass # Ignorar si OBS falla al actualizar el texto
