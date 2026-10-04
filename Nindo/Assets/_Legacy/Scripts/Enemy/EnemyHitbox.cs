using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class EnemyHitbox : MonoBehaviour
{

    public enum HitboxMode { Idle, Attack, Parry }
    public HitboxMode currentMode = HitboxMode.Idle;
    [SerializeField] Animator anim;
    [SerializeField] PlayerSwordAnimation PlayerSwordAnimation;
    [SerializeField] CapsuleCollider swordCollider;
    public bool isParying;
    [SerializeField] private ParticleSystem chispas;
    [SerializeField] private float chispasDuration = 0.05f;



    // Start is called before the first frame update
    void Start()
    {
        chispas.Stop();
        isParying = false;
    }

    // Update is called once per frame
    void Update()
    {
        AnimatorStateInfo animatorStateInfo = anim.GetCurrentAnimatorStateInfo(0);
        if (animatorStateInfo.IsName("EnemyParry"))
        {
            currentMode = HitboxMode.Parry;

        }
        else
        {
            isParying = false;
            swordCollider.enabled = false;
            gameObject.tag = "EnemySword";
        }
    }
    private void OnTriggerEnter(Collider other)
    {
        if (currentMode == HitboxMode.Parry & other.CompareTag("Player"))
        {
            PlayerSwordAnimation.InterrumptAttack();
            chispas.Play();
            Invoke("EndChispas", chispasDuration);
            anim.SetTrigger("endParry");

        }
    }
    public void StartParry()
    {
        gameObject.tag = "Parry";
        isParying = true;
        swordCollider.enabled = true;
    }
    public void EndParry()
    {
        isParying = false;
        swordCollider.enabled = false;
        gameObject.tag = "EnemySword";

    }
    public void EndChispas()
    {
        chispas.Stop();
    }
}
