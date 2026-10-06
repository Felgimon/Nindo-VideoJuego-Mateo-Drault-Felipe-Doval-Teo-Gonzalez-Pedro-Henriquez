using System.Collections;
using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// La presentación de Kokuyō y el final del juego. La presentación genérica (PlayBossIntroShot desde 6 m, FOV 34)
    /// le cortaba la cabeza a un jefe de 4.5 m y no mostraba lo que hay que mirar: su sombra en el piso.
    /// </summary>
    public partial class StoryDirector
    {
        static IEnumerator Wait(float s) { if (s > 0f) yield return new WaitForSecondsRealtime(s); }

        /// <summary>
        /// Primera vez: Kaito entra al patio y Kokuyō lo espera arrodillado (plano amplio y bajo) mientras habla; se
        /// levanta en una grúa baja que sube mirándolo, desenvaina con los braseros encendiéndose en ola desde él y se le
        /// encienden los ojos con el título. La luna rompe las nubes (KageArenaFX la muestra en el cielo) y, de vuelta en
        /// el patio, su sombra se estira por el piso hasta los pies de Kaito mientras el abuelo grita "¡Mirá el suelo!".
        /// Reintento (~4 s): se levanta desde la mitad, braseros, título corto y la sombra; sin diálogo ni cielo.
        /// </summary>
        IEnumerator KokuyoIntro(KokuyoBoss k)
        {
            bool first = !Game.Save.HasFlag(BossSeenFlag(k.bossId));
            var fx = k.ArenaFX;
            var clip = KokuyoTimings.Intro;
            Vector3 b = k.transform.position;
            Vector3 f = k.transform.forward.Flat().normalized;   // hacia Kaito (BossIntroRoutine ya lo giró)
            Vector3 right = Vector3.Cross(Vector3.up, f);
            Game.Audio?.StopMusic(first ? 1.5f : 0.6f);
            k.ScriptedPlay(KokuyoTimings.SeizaIdle.State, 0f);   // EnterScripted lo había parado
            int wide = -1;
            if (first)
            {
                // Kaito avanza hasta ~15 m de él (entra por la puerta a ~26 m): la pelea no arranca con 25 m de caminata
                if (CombatMath.FlatDistance(P.transform.position, b) > 16.5f) P.ScriptedMoveTo(b + f * 15f, 3.2f);
                wide = Game.Camera.PlayStaticShot(b + f * 26f + right * 2.5f + Vector3.up * 8f, b + Vector3.up * 2f, 34f, 0f, 1.2f, 1f);
                yield return Wait(1.8f);
                yield return Say("kage_intro");
            }
            float from = first ? 0f : clip.FrameNorm(36f);
            float sec = clip.Seconds, dur = (1f - from) * sec;
            k.PlayIntro(from);
            int crane = Game.Camera.PlayShot(t =>
            {
                float u = Mathf.SmoothStep(0f, 1f, Mathf.Clamp01(t / dur));
                Vector3 pos = b + f * Mathf.Lerp(8.5f, 9.5f, u) + right * Mathf.Lerp(3f, 2f, u) + Vector3.up * Mathf.Lerp(1.2f, 2.4f, u);
                Vector3 look = b + Vector3.up * Mathf.Lerp(2.4f, 4.3f, u);
                return new Pose(pos, Quaternion.LookRotation(look - pos));
            }, () => 36f, first ? 0.9f : 0f, dur + 0.5f, 0.8f);
            if (wide >= 0) Game.Camera.CancelShot(wide);
            // desenvaina (f60): los braseros se encienden en ola desde él; el chiburi y los ojos (f81): el título
            float draw = clip.FrameNorm(60f), eyes = clip.Event("EyesIgnite");
            yield return Wait((draw - from) * sec);
            // la primera vez el cielo llega 1.4 s después (la luna rompe las nubes); en el reintento se abren solas
            fx?.Intro(k.transform, first ? 1.4f : -1f);
            yield return Wait((eyes - Mathf.Max(from, draw)) * sec);
            k.EyesIgnite();
            Game.Audio?.Play("boss_roar", k.transform.position, first ? 1f : 0.8f);
            Game.Camera.Shake(0.3f);
            Game.UI.ShowAreaTitle(k.title, k.subtitle);
            yield return Wait((1f - eyes) * sec);
            Game.Camera.CancelShot(crane);
            if (first)
            {
                // el plano del cielo de KageArenaFX (1.4 + 1.0 + 2.8 s): al volver, la sombra ya está en el piso
                yield return Wait(4.0f);
                Vector3 kp = P.transform.position;
                int floor = Game.Camera.PlayStaticShot(kp - f * 4.5f + right * 1.5f + Vector3.up * 10f, Vector3.Lerp(kp, b, 0.45f), 36f, 0f, 1.0f, 0.9f);
                k.RevealShadow(1.3f);
                yield return Wait(1.4f);
                yield return Say("kage_intro_abuelo");
                Game.Camera.CancelShot(floor);
                Game.Save.SetFlag(BossSeenFlag(k.bossId));
                SaveSystem.Save();
            }
            else
            {
                k.RevealShadow(0.8f);
                yield return Wait(0.5f);
            }
            yield return Wait(0.3f);
            k.ExitScripted(false);
            k.BeginFight();
        }

        /// <summary>El jefe final ya vencido (sigue en el patio, en seiza).</summary>
        static KokuyoBoss FinalBoss()
        {
            if (Game.World == null) return null;
            foreach (var a in Game.World.Arenas) if (a != null && a.Boss is KokuyoBoss k) return k;
            return null;
        }

        /// <summary>
        /// El final: Kaito, el abuelo (las cuerdas de sombra se deshacen: está libre) y Kokuyō arrodillado y sin
        /// máscara, los tres en un plano de perfil (Kaito en el medio: es el lazo). En negro se los ubica: la pelea
        /// pudo terminar en cualquier punto del patio. Kaito le devuelve su media cinta y Kokuyō se inclina en seiza,
        /// la misma pose en la que lo esperaba. Después, a casa.
        /// </summary>
        IEnumerator EndingScene()
        {
            var gp = Game.World.Point("npc_grandpa_dojo");
            NPC grandpa = gp != null ? gp.GetComponent<NPC>() : null;
            if (grandpa == null) grandpa = NPC.Spawn("grandpa", P.transform.position + P.transform.forward * 3f, Quaternion.identity, null);
            var k = FinalBoss();
            var fx = k != null ? k.ArenaFX : KageArenaFX.Current;
            // la línea abuelo - Kaito - Kokuyō, perpendicular a la cámara (que mira desde el sudeste, como antes)
            Vector3 camOff = new Vector3(3.5f, 0f, -4.5f).normalized;
            Vector3 dir = Vector3.Cross(Vector3.up, camOff);
            Vector3 g = grandpa.transform.position;
            Vector3 kaitoSpot = OnNavMesh(g + dir * 2.4f);
            Vector3 kokuyoSpot = OnNavMesh(g + dir * 5.0f);
            yield return Game.UI.Fade(1f, 0.6f);
            P.Teleport(kaitoSpot, Quaternion.LookRotation(-dir));
            if (k != null) k.KneelAt(kokuyoSpot, Quaternion.LookRotation(-dir));
            Game.Camera?.Snap();
            P.ScriptedFace(g);
            Vector3 mid = k != null ? (g + kokuyoSpot) * 0.5f : (P.transform.position + g) * 0.5f;
            float back = k != null ? 1.35f : 1f;
            int shot = Game.Camera.PlayStaticShot(mid + new Vector3(3.5f, 2.6f, -4.5f) * back, mid + Vector3.up * 1.2f, 34f, 0f, 0f, 1f);
            yield return Game.UI.Fade(0f, 0.8f);
            // las cuerdas se deshacen (y su zumbido se apaga): recién libre, el abuelo se da vuelta hacia su nieto
            if (fx != null && fx.Ropes != null && fx.Ropes.Bound) { fx.Ropes.Dissolve(1.6f); yield return Wait(1.5f); }
            grandpa.FaceTo(P.transform.position);
            Game.FX.Petals(mid + Vector3.up * 2f, 2f);
            yield return Wait(0.4f);
            yield return Say("ending");
            if (k != null)
            {
                P.ScriptedFace(k.transform.position);
                k.Bow();
                yield return Wait(2.2f);
                P.ScriptedFace(g);
            }
            yield return Say("ending_final");
            Game.Camera.CancelShot(shot);
            Game.Save.SetFlag(Flags.Ending);
            SaveSystem.Save();
            yield return Game.UI.Fade(1f, 2f);
        }

        static Vector3 OnNavMesh(Vector3 p) =>
            UnityEngine.AI.NavMesh.SamplePosition(p, out var hit, 2f, UnityEngine.AI.NavMesh.AllAreas) ? hit.position : p;
    }
}
