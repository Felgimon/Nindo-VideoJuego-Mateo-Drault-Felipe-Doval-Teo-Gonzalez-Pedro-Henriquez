namespace Nindo
{
    /// <summary>
    /// Encuadre propio de un jefe. Si Game.Combat.ActiveBoss lo implementa, CameraDirector lo usa mientras dura la pelea
    /// (encima de eso siempre corre el auto-encuadre que aleja la cámara si la cabeza o el arma se salen por arriba).
    /// Un jefe sin este perfil usa el de combate con una distancia extra según su altura.
    /// </summary>
    public interface ICameraProfile
    {
        /// <summary>Inclinación absoluta en grados (52 = exploración, 45 = combate). 0 o menos = la de combate (más el
        /// ajuste de la zona). Un valor propio ignora el ajuste de la zona: el número del jefe es el final.</summary>
        float CameraPitch { get; }
        /// <summary>Metros que se suman a la distancia de combate (fijado o no). Reemplaza al extra por altura.</summary>
        float CameraExtraDistance { get; }
    }
}
