using System;
using UnityEngine;
using UnityEngine.VFX;

namespace Nindo
{
    /// <summary>
    /// Base de datos de contenido: todas las referencias a assets que el juego necesita en
    /// runtime (modelos, controladores, materiales, VFX, audio, sprites). Vive en
    /// Assets/Nindo/Resources/NindoContent.asset. El menú "Nindo/Contenido/Autocompletar"
    /// la rellena sola buscando assets por nombre si algo queda vacío.
    /// </summary>
    [CreateAssetMenu(menuName = "Nindo/Content Database", fileName = "NindoContent")]
    public class NindoContent : ScriptableObject
    {
        [Serializable]
        public class CharacterEntry
        {
            public string id;
            public GameObject model;
            public RuntimeAnimatorController controller;
            [Tooltip("Altura final en metros (el modelo se escala solo)")] public float height = 1.6f;
            public Material[] materialOverrides;
        }

        [Serializable]
        public class PropEntry
        {
            public string id;
            public GameObject model;
        }

        [Serializable]
        public class AudioEntry
        {
            public string key;
            public AudioClip[] clips;
            [Range(0, 1)] public float volume = 1f;
            [Range(0, 0.5f)] public float pitchVariance = 0.05f;
            public bool spatial = true;
        }

        [Header("Personajes")]
        public CharacterEntry[] characters = new CharacterEntry[0];

        [Header("Mundo")]
        public GameObject[] zones = new GameObject[0];
        public PropEntry[] props = new PropEntry[0];
        public TextAsset propsManifest;
        public TextAsset worldData;

        [Header("Materiales")]
        public Texture2D paletteTexture;
        public Material paletteMaterial;
        public Material emissiveMaterial;
        public Material foliageMaterial;
        [Tooltip("Follaje con viento (shader Nindo/Foliage Wind). Si el shader no compila se usa foliageMaterial.")]
        public Material foliageWindMaterial;
        public bool useFoliageWind = true;
        public Material waterMaterial;
        [Tooltip("Agua low-poly animada (shader Nindo/Water Lowpoly). Si el shader no compila se usa waterMaterial.")]
        public Material waterAnimatedMaterial;
        public bool useAnimatedWater = true;
        public Material trailMaterial;
        public Material ghostMaterial;
        public Material flashMaterial;
        public Material additiveMaterial;
        public Material alphaMaterial;
        public Material skyboxMaterial;

        [Header("VFX (VFX Graph del proyecto)")]
        public VisualEffectAsset vfxParry;
        public VisualEffectAsset vfxHit;
        public VisualEffectAsset vfxImpact;
        public VisualEffectAsset vfxDamaged;
        public VisualEffectAsset vfxSlay;
        public VisualEffectAsset vfxSlash;
        public VisualEffectAsset vfxLines;
        public VisualEffectAsset vfxAura;

        [Header("Audio")]
        public AudioEntry[] sfx = new AudioEntry[0];
        public AudioEntry[] music = new AudioEntry[0];
        public AudioEntry[] ambience = new AudioEntry[0];

        [Header("UI")]
        public Sprite healthFill;
        public Sprite healthFrame;
        public Sprite spiritFill;
        public Sprite spiritFrame;
        [Tooltip("Área (normalizada) del relleno dentro del marco de la barra")] public Rect healthFillArea = new Rect(0, 0, 1, 1);
        public Rect spiritFillArea = new Rect(0, 0, 1, 1);
        public Sprite menuEyesClosed;
        public Sprite menuEyesOpen;
        public Sprite logo;
        public Font titleFont;
        public Font bodyFont;

        // búsquedas por clave con diccionarios (se arman la primera vez que se usan)
        System.Collections.Generic.Dictionary<string, CharacterEntry> charMap;
        System.Collections.Generic.Dictionary<string, GameObject> propMap;
        System.Collections.Generic.Dictionary<string, AudioEntry> sfxMap, musicMap, ambMap;

        void OnValidate() => ClearCache();
        void OnEnable() => ClearCache();
        public void ClearCache() { charMap = null; propMap = null; sfxMap = musicMap = ambMap = null; }

        static System.Collections.Generic.Dictionary<string, T> Map<TE, T>(TE[] arr, Func<TE, string> key, Func<TE, T> val)
        {
            var d = new System.Collections.Generic.Dictionary<string, T>();
            if (arr != null) foreach (var e in arr) if (e != null && !string.IsNullOrEmpty(key(e)) && !d.ContainsKey(key(e))) d[key(e)] = val(e);
            return d;
        }

        public CharacterEntry Character(string id)
        {
            charMap ??= Map(characters, c => c.id, c => c);
            return id != null && charMap.TryGetValue(id, out var c) ? c : null;
        }

        public GameObject Prop(string id)
        {
            propMap ??= Map(props, p => p.id, p => p.model);
            return id != null && propMap.TryGetValue(id, out var m) ? m : null;
        }

        public AudioEntry Sfx(string key)
        {
            sfxMap ??= Map(sfx, a => a.key, a => a);
            return key != null && sfxMap.TryGetValue(key, out var a) ? a : null;
        }

        public AudioEntry Music(string key)
        {
            musicMap ??= Map(music, a => a.key, a => a);
            return key != null && musicMap.TryGetValue(key, out var a) ? a : null;
        }

        public AudioEntry Ambience(string key)
        {
            ambMap ??= Map(ambience, a => a.key, a => a);
            return key != null && ambMap.TryGetValue(key, out var a) ? a : null;
        }
    }
}
