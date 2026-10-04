using System.Collections;
    using System.Collections.Generic;
using UnityEngine;
using UnityEngine.VFX;
    public class EnemyBeingDamaged : MonoBehaviour
    {
        //seteados desde el inspector
        [SerializeField] private healthScript healthScript;
        [SerializeField] private EnemyCombat enemyCombat;
        [SerializeField] private EnemyHitbox hitbox;
        [SerializeField] private Rigidbody rb;
        [SerializeField] private Transform playerTransform;
        [SerializeField] Animator animator;
        [SerializeField] private GameObject enemyEntity;
        [SerializeField] private bool isBeingDamaged;
        [SerializeField] private float parriedTime;
        [SerializeField] private float parriedDuration;
        [SerializeField] private ManaBar manaBar;
        [SerializeField] private float attackManaGain = 5f;
        [SerializeField] private DesequilibroBar desequilibroBar;
        [SerializeField] private PlayerCombat playerCombat;
        [SerializeField] private WhteFlash whiteFlash;
    //knockback
        [SerializeField] private float knockbackForce;
        [SerializeField] private float knockbackDuration;
        [SerializeField] private EnemyMovement enemyMovement;
    

        //animaciones
        [SerializeField] public float stunDuration;
        [SerializeField] public float stunTimer;
        [SerializeField] public float safeTime; // no recibir muchos ataques en uno
        
    public bool isStunned = false;
        public bool superArmor = false; //no puede recibir mas stun


        //Script vida
        public float Health;
        public float maxHealthAmount;
        public float finisherThreshold = 20f;
        [SerializeField] private float damageAmount; //se va a cambiar a la espada este valor
        [SerializeField] private GameObject F;
        public bool isFinishable;


        //Parry
        public bool parryHit;
        public bool canParry;
        private bool hadMomentum;

        [SerializeField] private VisualEffect damagedVFX;

    void Start()
        {
            parriedTime = parriedDuration;
            Health = maxHealthAmount;
            healthScript.UpdateHealthBar(maxHealthAmount, Health);
        }

        // Update is called once per frame
        void Update()
        {
            if (isStunned)
            {
                stunTimer -= Time.deltaTime;
                if (stunTimer <= 0)
                {
                    animator.SetBool("isStunned", false);
                    isStunned = false;
                    //Agregar partículas o algún tipo de vfx

                }
            }

        if (animator.GetCurrentAnimatorStateInfo(0).IsName("Stunned"))
        {
            parriedTime -= Time.deltaTime;
            if (parriedTime <= 0)
            {
                parriedTime=parriedDuration;
                animator.SetBool("isStunned", false);
            }
        }
        if (Health <= finisherThreshold)
        {
            F.SetActive(true);
            isFinishable = true;
        }
        else
        {
            F.SetActive(false);
            isFinishable = false;

        }

        if (isBeingDamaged)
        {
            safeTime -= Time.deltaTime;
            if (safeTime <= 0)
            {
                isBeingDamaged = false;
                safeTime = 0.1f;
            }
        }
    }
    void OnTriggerEnter(Collider other)
    {
        if (other.CompareTag("PlayerSword") && !isBeingDamaged)
        {
            // Caso 1: ya está esperando un golpe para hacer parry
            if (canParry)
            {
                damagedVFX.Play();
                animator.SetTrigger("Parry");
                canParry = false;
                playerCombat.InterrumptAttack();
                enemyMovement.stayStill=false;
                return;
            }

            // Caso 2: tiene momentum → mini stun
            if (enemyCombat.currentMomentum > 0)
            {
                hadMomentum = true;
                enemyCombat.currentMomentum--;
                desequilibroBar.UpdateDesequilibrioBar(enemyCombat.maxMomentum, enemyCombat.currentMomentum);
                StartCoroutine(enemyCombat.MiniStun());

                // Si pierde todo el momentum → entrar en WaitParry
                if (enemyCombat.currentMomentum <= 0 && hadMomentum)
                {
                    animator.SetTrigger("WaitParry");
                    canParry = true;

                    hadMomentum = false;
                }
            }



            //Animaciones
            //stunTimer = stunDuration;
            //animator.SetBool("isStunned", true);
            StartCoroutine(StopAtDamage(0.07f));

            damagedVFX.Play();
            manaBar.gastarMana(-attackManaGain);
            isStunned = true;
            parryHit = true;
            isBeingDamaged = true;
            whiteFlash.Flash(); //flash blanco
            Health -= damageAmount;
            if (Health <= 0)
            {
                Invoke(nameof(Death), knockbackDuration);
            }
            healthScript.UpdateHealthBar(maxHealthAmount, Health);


        }
    }   
        
     IEnumerator StopAtDamage(float duration)
    {
        float originalTimeScale = Time.timeScale;
        Time.timeScale = 0f; // pausa total
        yield return new WaitForSecondsRealtime(duration);
        Time.timeScale = originalTimeScale;
    }
    public void Death()
    {
        isFinishable = false;
        Destroy(enemyEntity);
        //Agregar partículas o algún tipo de vfx
    }
}
