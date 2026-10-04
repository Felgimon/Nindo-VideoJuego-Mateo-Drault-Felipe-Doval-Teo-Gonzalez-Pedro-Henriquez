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
        public Material waterMaterial;
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

        public CharacterEntry Character(string id)
        {
            if (characters == null) return null;
            foreach (var c in characters) if (c != null && c.id == id) return c;
            return null;
        }

        public GameObject Prop(string id)
        {
            if (props == null) return null;
            foreach (var p in props) if (p != null && p.id == id) return p.model;
            return null;
        }

        public AudioEntry Sfx(string key)
        {
            if (sfx == null) return null;
            foreach (var a in sfx) if (a != null && a.key == key) return a;
            return null;
        }

        public AudioEntry Music(string key)
        {
            if (music == null) return null;
            foreach (var a in music) if (a != null && a.key == key) return a;
            return null;
        }

        public AudioEntry Ambience(string key)
        {
            if (ambience == null) return null;
            foreach (var a in ambience) if (a != null && a.key == key) return a;
            return null;
        }
    }
}
