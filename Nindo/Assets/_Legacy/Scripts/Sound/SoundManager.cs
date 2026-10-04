using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

public enum SoundType
{
    ATTACK,
    PARRY,
    HURT,
    FOOTSTEPS,
    BACKGROUND,
    FINISHER,
    DASH,
    MENU
}

public class SoundManager : MonoBehaviour
{
    [SerializeField] private AudioClip[] soundList;
    [SerializeField, Range(0, 1f)] public float musicVolume = 0.2f;
    [SerializeField, Range(0, 1f)] public float masterVolume = 1.0f;
    [SerializeField, Range(0, 1f)] public float sfxVolume = 1.0f;
    [SerializeField] private float fadeDuration = 3f;
    Transform MenuTr;
    Transform OptionsMenuTr;
    [SerializeField] bool isInMenu;
    [SerializeField] bool isInGameplay;
    private bool isFading = false;
    private static SoundManager instance; // Singleton instance
    private AudioSource sfxSource;
    private AudioSource musicSource;
    private Slider masterSlider;
    private Slider musicSlider;
    private Slider sfxSlider;

    private void Awake()
    {
        if (instance == null)
        {
            instance = this;

            //Se mantiene la misma instancia al cambiar de escena
            DontDestroyOnLoad(gameObject);

            //Suscribo el metodo OnSceneLoaded al evento sceneLoaded
            SceneManager.sceneLoaded += OnSceneLoaded;

            //Creo los AudioSources
            sfxSource = gameObject.AddComponent<AudioSource>();
            musicSource = gameObject.AddComponent<AudioSource>();
        }
        else if (instance != this)
        {
            Destroy(gameObject);
            return;
        }
    }

    private void Update()
    {
        if (!isFading)
            musicSource.volume = musicVolume * masterVolume; //Para que sea configurable en realtime

    }

    private void OnSceneLoaded(Scene scene, LoadSceneMode mode)
    {
        if (scene.name == "Menu")
        {
            isInMenu = true;
            isInGameplay = false;
        }
        else
        {
            isInMenu = false;
            isInGameplay = true;
        }
        PlayMusic();
        
        MenuTr = GameObject.Find("Menu").GetComponent<Transform>();
        Transform MenuContainerTr = MenuTr.Find("MenuContainer")?.GetComponent<Transform>();
        if (MenuContainerTr == null) // El signo de pregunta: *Adjuntar foto de superman esperanzado*
        {
            OptionsMenuTr = MenuTr.Find("OptionsMenu").GetComponent<Transform>(); // En el caso del menu principal
        } else
        {
            OptionsMenuTr = MenuContainerTr.Find("OptionsMenu").GetComponent<Transform>(); // En el caso de menu de pausa
        }


        masterSlider = OptionsMenuTr.Find("MasterSlider").GetComponent<Slider>();
        musicSlider = OptionsMenuTr.Find("MusicSlider").GetComponent<Slider>();
        sfxSlider = OptionsMenuTr.Find("SfxSlider").GetComponent<Slider>();

        //Seteo los sliders al valor de los volumenes
        musicSlider.value = musicVolume;
        masterSlider.value = masterVolume;
        sfxSlider.value = sfxVolume;

        //Listeners que para cuando se muevan ejecuten las funciones que actualizan los volumenes
        musicSlider.onValueChanged.AddListener(MusicVolumeSettings);
        masterSlider.onValueChanged.AddListener(MasterVolumeSettings);
        sfxSlider.onValueChanged.AddListener(SfxVolumeSettings);

    }

    private void PlayMusic()
    {
        musicSource.loop = true;
        musicSource.volume = musicVolume * masterVolume;
        if (isInMenu) //Si estoy en el menu, que ponga la musica del menu
        {
            musicSource.clip = soundList[(int)SoundType.MENU];
        }
        else if (isInGameplay) //Si estoy en el gameplay, que ponga la musica del gameplay
        {
            musicSource.clip = soundList[(int)SoundType.BACKGROUND];
        }
        musicSource.Play();
    }

    //static volumes for PlaySound()
    public static float SavedMasterVolume => instance.masterVolume;
    public static float SavedSfxVolume => instance.sfxVolume;


    public static void PlaySound(SoundType sound, float volume = 1)
    {
        instance.sfxSource.PlayOneShot(instance.soundList[(int)sound], volume * SavedMasterVolume * SavedSfxVolume); // Reproduce el sonido que le pasas que corresponda al enum y setea el volumen de ese audio
    }

    public void MusicVolumeSettings(float volume)
    {
        musicVolume = volume;
    }
    public void MasterVolumeSettings(float volume)
    {
        masterVolume = volume;
    }
    public void SfxVolumeSettings(float volume)
    {
        sfxVolume = volume;
    }

    public void FadeOut()
    {
        if (!isFading)
            StartCoroutine(FadeOutCoroutine());
    }

    private IEnumerator FadeOutCoroutine()
    {
        isFading = true;

        float startVolume = musicSource.volume;
        float t = 0;

        while (t < fadeDuration)
        {
            t += Time.deltaTime;
            musicSource.volume = Mathf.Lerp(startVolume, 0, t / fadeDuration);
            yield return null;
        }

        musicSource.Stop();
        isFading = false;
    }

}
