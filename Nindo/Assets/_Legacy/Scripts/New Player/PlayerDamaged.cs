using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class PlayerDamaged : MonoBehaviour
{
    [SerializeField] PlayerLifeManager playerLifeManager;
    [SerializeField] PlayerCombat playerCombat;

    public float enemyDamage;
    public bool hasRecievedDamage = false;
    public float invincibilityDuration;
    public GameObject owner;

    // Start is called before the first frame update
    void Start()
    {
    }
    // Update is called once per frame
    void Update()
    {
        
    }

//    private void OnTriggerEnter(Collider other)
//  {
//        if (other.CompareTag("EnemySword") && !hasRecievedDamage && this.CompareTag("PlayerBody") && !playerCombat.hasParried)
//        {
//            playerLifeManage.DamageTaken(enemyDamage);
//            Invoke("RestartInvincibility", invincibilityDuration);
//            hasRecievedDamage = true;
            
//        }
//    }
    public void TakeDamage()
    {
        playerLifeManager.DamageTaken(enemyDamage);
        Invoke("RestartInvincibility", invincibilityDuration);
        hasRecievedDamage = true;
    }
    void RestartInvincibility()
    {
        hasRecievedDamage = false;
    }
}
