 using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class PlayerSwordAnimation : MonoBehaviour
{
    public Animator animator;
    public bool isAttacking;
    public BoxCollider swordCollider;
    public bool isStunned;

    [Header("Attack Movement")]
    public float attackDashSpeed = 5f;//velocidad del dash
    public float attackDashTime = 0.15f;//duración del dash en segundos
    private bool isDashing = false;
    [SerializeField] private Renderer playerRenderer;

    [SerializeField] private PlayerMovement playerMovement; //ARREGLAR
    void Awake()
    {
        if (playerRenderer == null)
            playerRenderer = GetComponent<Renderer>();
    }

    void Start()
    {
        isAttacking = false;
    }

    void Update()
    {
        if (Input.GetKeyDown(KeyCode.Space))
        {
            SwordHit();
        }
    }

    public void SwordHit()
    {
        if (!animator.GetCurrentAnimatorStateInfo(0).IsName("Golpe"))//animación de ataque
        {
            animator.SetTrigger("pHit");
        }
    }
    public void DoAttackDash()
    {
        StartCoroutine(AttackDash());
    }
    public void StopAttacking()
    {
        isAttacking = false;
        swordCollider.enabled = false;
    }

    public void StartAttaking()
    {
        swordCollider.enabled = true;
        isAttacking = true;
    }

    public void InterrumptAttack()
    {
        if (isAttacking)
        {
            animator.SetTrigger("stunned");
            animator.ResetTrigger("pHit");
            isAttacking = false;
            swordCollider.enabled = false;
        }
    }

    private IEnumerator AttackDash()
    {
        if (isDashing) yield break;//evita que se solapen dashes

        isDashing = true;
        float timer = 0f;

        while (timer < attackDashTime)
        {
            transform.position += transform.forward * attackDashSpeed * Time.deltaTime; //ARREGLARRR
            Debug.Log("Daleeee");
            timer += Time.deltaTime;
            yield return null;
        }

        isDashing = false;
    }
}
