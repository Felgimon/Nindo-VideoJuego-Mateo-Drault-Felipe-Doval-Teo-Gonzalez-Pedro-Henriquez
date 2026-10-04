using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class PlayerBeingDamaged : MonoBehaviour
{
    [SerializeField] private float enemySwordDamage; //esto va a la espada del enemigo mas adelante
    [SerializeField] private PlayerLifeManager playerLifeManager;
    public bool hasRecivedDamage = false;
    public Material originalMaterial;
    public Material newMaterial;

    [SerializeField] private float invincibilityDuration;
    [SerializeField] private Renderer playerRenderer;

    [SerializeField] private PlayerParry PlayerParry;

    // Start is called before the first frame update
    void Start()
    {

    }

    // Update is called once per frame
    void Update()
    {
        
    }
    private void OnTriggerEnter(Collider other)
    {
        if (other.CompareTag("EnemySword") && !hasRecivedDamage)
        {
            Debug.Log("daño");
            playerRenderer.material = newMaterial;
            hasRecivedDamage = true;
            playerLifeManager.DamageTaken(enemySwordDamage);
            Invoke("RestartInvincibility", invincibilityDuration);
        }
    }
    public void RestartInvincibility()
    {
        Debug.Log("ended");
        hasRecivedDamage = false;
    }
}
