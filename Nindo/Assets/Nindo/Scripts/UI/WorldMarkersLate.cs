using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Las barras, la mira y los avisos sobre el mundo se proyectan con la pose final de la cámara:
    /// CameraDirector la fija en su LateUpdate (orden 500), así que esto corre después. Si se
    /// proyectaban en el Update de UIManager quedaban un cuadro atrás y "nadaban" al girar o en los temblores.
    /// (Va en su propio archivo: Unity toma DefaultExecutionOrder del script, no de una clase anidada.)
    /// </summary>
    [DefaultExecutionOrder(600)]
    public class WorldMarkersLate : MonoBehaviour
    {
        public UIManager ui;
        void LateUpdate() { if (ui != null) ui.UpdateWorldMarkers(Time.unscaledDeltaTime); }
    }
}
