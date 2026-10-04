using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Nindo.EditorTools
{
    /// <summary>
    /// Herramientas del menú "Nindo" para trabajar sin los scripts de Python:
    ///  * Validar: lista todo lo que falta en NindoContent (modelos, controllers, audio...).
    ///  * Autocompletar: agrega props, zonas y clips de audio nuevos buscando por convención de
    ///    nombres (Art/Models/Props/&lt;id&gt;.fbx, Art/Models/World/*.fbx, Audio/Sfx/&lt;clave&gt;_&lt;n&gt;.wav...).
    ///  * Jugar desde el menú: abre Menu.unity y entra en Play.
    /// </summary>
    public static class NindoContentTools
    {
        const string ContentPath = "Assets/Nindo/Resources/NindoContent.asset";
        const string PropsDir = "Assets/Nindo/Art/Models/Props";
        const string WorldDir = "Assets/Nindo/Art/Models/World";
        const string AudioDir = "Assets/Nindo/Audio";

        static NindoContent Load()
        {
            var c = AssetDatabase.LoadAssetAtPath<NindoContent>(ContentPath);
            if (c == null) Debug.LogError("[Nindo] No encuentro " + ContentPath);
            return c;
        }

        [MenuItem("Nindo/Contenido/Validar")]
        public static void Validate()
        {
            var c = Load();
            if (c == null) return;
            var problems = new List<string>();
            foreach (var ch in c.characters)
            {
                if (ch.model == null) problems.Add($"Personaje '{ch.id}': falta el modelo");
                if (ch.controller == null) problems.Add($"Personaje '{ch.id}': falta el AnimatorController");
            }
            if (c.zones == null || c.zones.Length == 0 || c.zones.Any(z => z == null)) problems.Add("Zonas del mundo vacías o con huecos");
            foreach (var p in c.props) if (p.model == null) problems.Add($"Prop '{p.id}': falta el modelo");
            if (c.propsManifest == null) problems.Add("Falta PropsManifest.json");
            else
            {
                var ids = new HashSet<string>(c.props.Select(p => p.id));
                foreach (Match m in Regex.Matches(c.propsManifest.text, "\"id\":\\s*\"([^\"]+)\""))
                    if (!ids.Contains(m.Groups[1].Value)) problems.Add($"El manifest tiene '{m.Groups[1].Value}' pero NindoContent no");
            }
            void Audio(string kind, NindoContent.AudioEntry[] arr)
            {
                foreach (var a in arr)
                    if (a.clips == null || a.clips.Length == 0 || a.clips.Any(x => x == null)) problems.Add($"{kind} '{a.key}': clips vacíos");
            }
            Audio("Sfx", c.sfx); Audio("Música", c.music); Audio("Ambiente", c.ambience);
            foreach (var key in new[] { "menu", "explore", "combat", "boss" })
                if (c.Music(key) == null) problems.Add($"Música '{key}' no existe");
            if (c.paletteMaterial == null || c.emissiveMaterial == null || c.foliageMaterial == null || c.waterMaterial == null)
                problems.Add("Faltan materiales base (paleta/emisivo/follaje/agua)");
            if (c.skyboxMaterial == null) problems.Add("Falta el material del cielo");

            if (problems.Count == 0) Debug.Log($"[Nindo] Contenido OK: {c.characters.Length} personajes, {c.props.Length} props, {c.zones.Length} zonas, {c.sfx.Length} efectos, {c.music.Length} temas, {c.ambience.Length} ambientes.");
            else Debug.LogWarning("[Nindo] Problemas en NindoContent:\n - " + string.Join("\n - ", problems));
        }

        [MenuItem("Nindo/Contenido/Autocompletar")]
        public static void AutoFill()
        {
            var c = Load();
            if (c == null) return;
            Undo.RecordObject(c, "Autocompletar NindoContent");
            int added = 0;

            // props: un FBX por id
            var props = c.props.ToList();
            foreach (var path in Files(PropsDir, "*.fbx"))
            {
                string id = Path.GetFileNameWithoutExtension(path);
                var e = props.FirstOrDefault(p => p.id == id);
                var model = AssetDatabase.LoadAssetAtPath<GameObject>(path);
                if (e == null) { props.Add(new NindoContent.PropEntry { id = id, model = model }); added++; }
                else if (e.model == null) { e.model = model; added++; }
            }
            c.props = props.OrderBy(p => p.id).ToArray();

            // zonas del mundo
            var zones = Files(WorldDir, "*.fbx").Select(AssetDatabase.LoadAssetAtPath<GameObject>).Where(g => g != null).ToArray();
            if (zones.Length > 0 && (c.zones == null || c.zones.Length != zones.Length || c.zones.Any(z => z == null))) { c.zones = zones; added++; }

            // audio: Sfx/<clave>_<n>.wav, Music/<clave>.ogg, Ambience/<clave>.ogg
            added += FillAudio(ref c.sfx, "Sfx", true);
            added += FillAudio(ref c.music, "Music", false);
            added += FillAudio(ref c.ambience, "Ambience", false);

            c.ClearCache();
            EditorUtility.SetDirty(c);
            AssetDatabase.SaveAssets();
            Debug.Log($"[Nindo] Autocompletar: {added} cambios.");
            Validate();
        }

        static int FillAudio(ref NindoContent.AudioEntry[] arr, string folder, bool numbered)
        {
            int added = 0;
            var list = (arr ?? new NindoContent.AudioEntry[0]).ToList();
            var groups = new Dictionary<string, List<AudioClip>>();
            foreach (var path in Files(Path.Combine(AudioDir, folder), "*.*"))
            {
                var clip = AssetDatabase.LoadAssetAtPath<AudioClip>(path);
                if (clip == null) continue;
                string key = Path.GetFileNameWithoutExtension(path);
                if (numbered) key = Regex.Replace(key, "_\\d+$", "");
                if (!groups.TryGetValue(key, out var l)) groups[key] = l = new List<AudioClip>();
                l.Add(clip);
            }
            foreach (var kv in groups)
            {
                var e = list.FirstOrDefault(a => a.key == kv.Key);
                if (e == null)
                {
                    list.Add(new NindoContent.AudioEntry { key = kv.Key, clips = kv.Value.ToArray(), volume = folder == "Sfx" ? 1f : folder == "Music" ? 0.8f : 0.45f, spatial = folder == "Sfx" && !kv.Key.StartsWith("ui_") });
                    added++;
                }
                else
                {
                    var merged = (e.clips ?? new AudioClip[0]).Where(x => x != null).Union(kv.Value).ToArray();
                    if (e.clips == null || merged.Length != e.clips.Length) { e.clips = merged; added++; }
                }
            }
            arr = list.OrderBy(a => a.key).ToArray();
            return added;
        }

        static IEnumerable<string> Files(string dir, string pattern)
        {
            if (!Directory.Exists(dir)) return Enumerable.Empty<string>();
            return Directory.GetFiles(dir, pattern).Where(f => !f.EndsWith(".meta")).Select(f => f.Replace('\\', '/')).OrderBy(f => f);
        }

        [MenuItem("Nindo/Jugar desde el menú %#p")]
        public static void PlayFromMenu()
        {
            if (EditorApplication.isPlaying) { EditorApplication.isPlaying = false; return; }
            if (!EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo()) return;
            EditorSceneManager.OpenScene("Assets/Nindo/Scenes/Menu.unity");
            EditorApplication.isPlaying = true;
        }

        [MenuItem("Nindo/Borrar partida guardada")]
        public static void DeleteSave()
        {
            SaveSystem.Delete();
            Debug.Log("[Nindo] Partida borrada.");
        }
    }
}
