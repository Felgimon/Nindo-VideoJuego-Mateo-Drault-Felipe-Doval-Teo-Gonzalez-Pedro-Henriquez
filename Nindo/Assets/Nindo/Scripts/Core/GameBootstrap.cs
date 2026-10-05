using System.Collections;
using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Arranque de la escena de juego. La escena "Nindo" solo contiene este componente:
    /// todo lo demás (mundo, Kaito, enemigos, cámara, UI, audio) se arma por código a partir
    /// de NindoContent. Así la escena es liviana, no se rompe al mover assets y cualquier
    /// integrante del equipo puede darle Play sin configurar nada.
    /// </summary>
    [DefaultExecutionOrder(-1000)]
    public class GameBootstrap : MonoBehaviour
    {
        [Tooltip("Para probar rápido desde el editor: arranca en este santuario (vacío = según la partida)")]
        public string debugStartCheckpoint = "";
        [Tooltip("Desbloquea dash y habilidades desde el inicio (solo pruebas)")]
        public bool debugUnlockAll;
        [Tooltip("Saltear el prólogo (solo pruebas)")]
        public bool debugSkipIntro;

        IEnumerator Start()
        {
            Application.targetFrameRate = 120;
            QualitySettings.vSyncCount = 1;
            if (Settings.Quality >= 0 && Settings.Quality < QualitySettings.names.Length) QualitySettings.SetQualityLevel(Settings.Quality, true);
            Cursor.visible = false;

            Game.LoadContent();
            // si se le da Play directo a esta escena (sin pasar por el menú) se continúa la partida
            if (!SceneFlow.CameFromMenu) { if (SaveSystem.HasSave) SaveSystem.Load(); else SaveSystem.NewGame(); }
            // arrancar en un santuario implica saltear el prólogo (si no, el checkpoint se ignoraba sin aviso)
            if (debugSkipIntro || !string.IsNullOrEmpty(debugStartCheckpoint)) { Game.Save.SetFlag(Flags.IntroDone); Game.Save.SetFlag(Flags.KatanaObtained); Game.Save.SetFlag("enc_intro"); }

            // ---------------------------------------------------------- sistemas
            var systems = new GameObject("[Nindo Systems]");
            systems.AddComponent<TimeController>();
            systems.AddComponent<InputReader>();
            systems.AddComponent<CombatDirector>();
            systems.AddComponent<FXManager>();
            systems.AddComponent<StoryDirector>();
            AudioManager.Ensure();
            var ui = new GameObject("[UI]").AddComponent<UIManager>();
            ui.SetFade(1f);
            var cam = Camera.main != null ? Camera.main.gameObject : new GameObject("Main Camera");
            if (cam.GetComponent<CameraDirector>() == null) cam.AddComponent<CameraDirector>();
            var world = new GameObject("[WorldBuilder]").AddComponent<WorldBuilder>();
            world.SetupLighting();

            // ---------------------------------------------------------- mundo
            yield return world.Build();

            // ---------------------------------------------------------- Kaito
            Vector3 pos = world.StartPoint; Quaternion rot = world.StartRotation;
            string cpId = !string.IsNullOrEmpty(debugStartCheckpoint) ? debugStartCheckpoint : Game.Save.checkpoint;
            var cp = Checkpoint.Get(cpId);
            if (cp != null && Game.Save.HasFlag(Flags.IntroDone))
            {
                pos = cp.spawnPoint.position; rot = cp.spawnPoint.rotation;
                if (!string.IsNullOrEmpty(debugStartCheckpoint)) Game.Save.checkpoint = cp.id;   // y reaparecer ahí al morir
            }
            // el prólogo arranca en negro: sin título de zona en el frame intermedio (Intro lo vuelve a poner igual)
            if (!Game.Save.HasFlag(Flags.IntroDone)) Game.InCutscene = true;
            var player = CharacterFactory.BuildPlayer(pos + Vector3.up * 0.1f, rot);
            player.debugUnlockAll = debugUnlockAll;
            yield return null;
            Game.Camera.Snap();

            // la zona ya eligió su música y su ambiente en el frame intermedio (antes se pisaban con los genéricos);
            // si en ese frame arrancó una pelea (se continúa dentro del radio de un encuentro) queda la de combate
            if (Game.Combat == null || !Game.Combat.InCombat) Game.Audio.PlayMusic(Zone.Current != null ? Zone.Current.music : "explore", 2f);
            Game.Story.Begin(SceneFlow.NewGameRequested);
            if (Zone.Current == null) Game.Audio.PlayAmbience("night");
        }

        void Update()
        {
            if (Game.Save != null) Game.Save.playTime += Time.unscaledDeltaTime;
        }

        void OnApplicationQuit() => SaveSystem.Save();
    }
}
