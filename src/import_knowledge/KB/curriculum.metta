!(assert (if (or (and true false) true) 1 2) 1)
;;;;;;;NEXT EXAMPLE:
!(assert (cons-atom 0 (1 2 3))
       (0 1 2 3))

!(assert (car-atom (1 2 3))
       1)

!(assert (cdr-atom (1 2 3))
       (2 3))

!(assert (index-atom (1 2 3) 1)
       2)

!(assert (id 5) 5)

!(assert (=alpha (Father $X) (Father $Y)) True)

!(assert (=alpha (Father $X) (Son $X)) False)

!(assert (first-from-pair (A B)) A)

!(assert (second-from-pair (A B)) B)
;;;;;;;NEXT EXAMPLE:
!(assert (if (and (or $x True) $y) ($x $y))
       ((True True) (False True)))
;;;;;;;NEXT EXAMPLE:
(= (fib $N)
   (if (< $N 2)
       $N
       (+ (fib (- $N 1))
          (fib (- $N 2)))))

(= (myfunc)
   5)

(= (call-fib)
   (call (fib (myfunc))))

(= (quote-fib)
   (quote (fib (myfunc))))

(= (eval-fib)
   (eval (fib (myfunc))))

(= (reduce-fib)
   (reduce (fib (myfunc))))

!(assert (fib-call (call-fib)) (fib-call 5))
!(assert (fib-quote (quote-fib)) (fib-quote (quote (fib (myfunc)))))
!(assert (fib-eval (eval-fib)) (fib-eval 5))
!(assert (fib-reduce (reduce-fib)) (fib-reduce 5))
;;;;;;;NEXT EXAMPLE:
(= (compile $stmt)
   (case $stmt
         (($stmt (superpose (what what2))))))

!(assert (collapse (compile wat))
       (what what2))
;;;;;;;NEXT EXAMPLE:
!(assert (case (1 2 3) ( ( (cons $h $t) $h) ) ) 1)
;;;;;;;NEXT EXAMPLE:
(= (wu) (case (empty)
              ((1 2)
               (Empty 42))))

(= (f) 42)

(= (wu2) (case (f)
               ((42 ok)
                (Empty nok))))

!(assert (wu) 42)
!(assert (wu2) ok)
;;;;;;;NEXT EXAMPLE:
(= (casetest $x)
   (case $x ((4 42)
             ($otherpattern 44)
             ($otherother $45))))
   
!(assert (casetest 5) 44)
;;;;;;;NEXT EXAMPLE:
(= (wu1)
   (empty))

(= (wu2)
   (full))

(= (wu)
   (superpose ((wu1)
               (wu2))))

!(assert (wu)
       (full))
;;;;;;;NEXT EXAMPLE:
; Chain example tests
!(assert (chain (+ 2 4) $n (* 3 $n)) 
       18)

!(assert (chain (+ 1 3) $n (chain (* 2 $n) $m (+ $n $m))) 
       12);;;;;;;NEXT EXAMPLE:
!(assert (collapse (1 2 3))
       ((1 2 3)))
;;;;;;;NEXT EXAMPLE:
(= (f) ;with a comment
   ;this is a line with just a comment
   42) ;overall we tested systematically several comments

!(assert (f) 42);and added an evil comment for fun
;anything else to comment?
;;;;;;;NEXT EXAMPLE:
;h just expects a structure:
(= (h (justdata haha $B) $C)
   (+ $B $C))

;just structure matching (check out listhead.metta for list structure matching)
!(assert (h (justdata haha 30) 40) 70)

;Please see listhead.metta next!
;;;;;;;NEXT EXAMPLE:
(foo 1)
(foo 2)

(= (match-single $space $pat $ret)
   (let* (($x (match $space $pat $ret))
          ($temp (cut)))
         $x))

!(let $x (match-single &self (foo $1) $1) (add-atom &self (bar $x)))

!(assert (collapse (match &self (bar $1) (bar $1)))
       ((bar 1)))
;;;;;;;NEXT EXAMPLE:
(= (y) (empty))

!(assert (collapse (y))
       ())
;;;;;;;NEXT EXAMPLE:
(= (f $L $a $b)
   (let $result (+ $a $b)
        (append ($result) $L)))

;Match does not automatically interpret the returned pattern as code:
;!(match &self (= (f 40.7 2) $x) $x)

;But we can eval after it if we desire (invokes translator.pl and calls the translated goals):
!(assert (let $fbody_specialized (match &self (= (f (42) 40.7 2) $x) $x) (eval $fbody_specialized))
       (42.7 42))

;Additionally we can emulate eval by using add-atom and remove-atom (not recommended):
(= (evalCustom $body)
   (let* (($a   (add-atom &self (= (myfunc) $body)))
          ($res (reduce (myfunc)))
          ($r   (remove-atom &self (= (myfunc) $body))))
         $res))

!(assert (evalCustom (match &self (= (f (42) 40.7 2) $x) $x))
       (42.7 42))
;;;;;;;NEXT EXAMPLE:
(= (facF $n)
   (if (== $n 0)
       1
       (* $n (facF (- $n 1)))))

!(assert (facF 10) 3628800)
;;;;;;;NEXT EXAMPLE:
!(add-atom &self (= (fib $N)
                    (if (< $N 2)
                        $N
                        (+ (fib (- $N 1))
                           (fib (- $N 2))))))

!(assert (fib 30) 832040)
;;;;;;;NEXT EXAMPLE:
(= (fib $N)
   (if (< $N 2)
       $N
       (+ (fib (- $N 1))
          (fib (- $N 2)))))

!(assert (fib 30) 832040)
;;;;;;;NEXT EXAMPLE:
!(import! &self fibsmart)

!(assert (fib 100) 354224848179261915075)
;;;;;;;NEXT EXAMPLE:
(= (fib-tr $n $a $b)
   (if (== $n 0)
       $a
       (fib-tr (- $n 1) $b (+ $a $b))))

(= (fib $n)
   (fib-tr $n 0 1))

!(assert (fib 100) 354224848179261915075)
;;;;;;;NEXT EXAMPLE:
(kb 1)
(kb 2)

!(assert (foldall + (match &self (kb $n) (+ $n 1)) 0)
       5)

(= (f) 1)
(= (f) 2)

!(assert (foldall + (let $x (f) (+ 1 $x)) 0)
        5)
;;;;;;;NEXT EXAMPLE:
(foo 1)
(foo 2)
(foo 3)

(= (countitem) (let $x (match &self (foo $1) (foo $1)) 1))
(= (merge $a $b) (+ $a $b))
(= (spacecount $x) (foldall merge (countitem) 0))

!(assert (foldall merge (countitem) 0) 3)
;;;;;;;NEXT EXAMPLE:
;Check out functionhead.metta!
(= (living garfield) True)
(= (being garfield) True)
(= (small garfield) True)
(= (living snoopy) True)
(= (being snoopy) True)
(= (being roomba) True)
(= (small roomba) True)
(= (living cat42) True)
(= (being cat42) True)
(= (small cat42) True)

(= (only $C $X)
   (let $constraint $C $X))

(= (animal $X)
   (only ((living $X) (being $X)) $X))

(= (cat (animal $X))
   (only (small $X) $X))

!(assert (msort (collapse (cat $X)))
       (cat42 garfield))
;Check out functionhead3.metta!
;;;;;;;NEXT EXAMPLE:
;Check out functionhead2.metta!
(= (in $x $L)
   (let True (is-member $x $L) $x))

(= (myplus (in $X (1 2 3)) 
           (in $Y (2 3)))
   (in (+ $X $Y) (3 4 5)))

;fine:
!(assert (collapse (myplus 1 3)) (4))
;output out of range:
!(assert (collapse (myplus 3 3)) ())
;input out of range:
!(assert (collapse (myplus 3 4)) ())
;what can be reached when adding $X to 3:
!(assert (collapse (myplus $x 3)) (4 5))
;what can be reached when adding $X to $Y:
!(assert (collapse (myplus $x $y)) (3 4 4 5 5))
;With which $x added to 2 can we reach values above 3 with myplus?
!(assert (collapse (let True (> (myplus $x 2) 3) $x)) (2 3))
;;;;;;;NEXT EXAMPLE:
;First take a look at constanthead.metta and listhead.metta
(= (myfunc $A $B)
   (append (append (42) $A) $B))

;Consider the following,
;we want to constrain an argument to be the return value of a function call:
;(see invertfunction.metta now to see that in pure form)
(= (h_old $A $C)
   (if (= $A (myfunc (10) $B)) ;= is also unification in PeTTa
       ($B $C)
       (empty)))

;Assuming we can arbitrarily parametrize functions (e.g. invert them as a special case)
;we can also constrain input argument values to correspond to the return value:
;thereby not only constraining what input arguments qualify to call the function
;but also constraining variables therein establishing a relational dependency:
(= (h (myfunc (10) $B) $C)
   ($B $C))

;lets try:
!(assert (h (42 10 40) 42000)
       ((40) 42000))
;same as in the old formulation:
!(assert (h_old (42 10 40) 42000)
       ((40) 42000))

;Check out functionhead2.metta!
;;;;;;;NEXT EXAMPLE:
(= (g $x) (+ $x 1))

(= (f $g) ($g 1))
(= (f $g) 42)

!(assert (collapse (f g)) (2 42))

!(remove-atom &self (= (f $g) 42))

!(assert (collapse (f g)) (2))

!(add-atom &self (= (f $g) 42))

!(remove-atom &self (= (f $g) ($g 1)))

!(assert (collapse (f g)) (42))

!(remove-atom &self (= (f $g) 42))

!(assert (collapse (f g)) ((f g)))
;;;;;;;NEXT EXAMPLE:
(= (g $x) (+ $x 1))

(= (f $g) ($g 1))
(= (f $g) ($g 2))

!(assert (collapse (f g)) (2 3))

!(remove-atom &self (= (f $g) ($g 1)))

;should still call a specialized function even though in this case it is only specialization of (= (f $g) ($g 2)) left.
!(assert (f g) 3)

!(add-atom &self (= (f $g) ($g 1)))

!(assert (f g) (3 2))
;;;;;;;NEXT EXAMPLE:
(: wu1 (-> Number Expression Expression))
(= (wu1 $a $b)
   (42 $a $b))

(: wu2 (-> Number Number Number))
(= (wu2 $a $b)
   (+ $a $b))

(: wu3 (-> Number Number %Undefined%))
(= (wu3 $a $b)
   (if (< $a 10)
       (+ $a $b)
       (a list not a number)))

!(assert (wu1 (+ 2 4) (+ 4 2)) (quote (42 6 (+ 4 2))))

!(assert (wu2 (+ 2 4) (+ 4 2)) 12)

!(assert (wu3 42 0) (a list not a number))

!(assert (wu3 2 0) 2)
;;;;;;;NEXT EXAMPLE:
!(assert (pow-math 2 3) 8)
!(assert (sqrt-math 9) 3.0)
!(assert (abs-math -5) 5)
!(assert (log-math 10 100) 2.0)
!(assert (trunc-math 5.6) 5)
!(assert (ceil-math 5.2) 6)
!(assert (floor-math 5.8) 5)
!(assert (round-math 5.4) 5)
!(assert (round-math 5.6) 6)
!(assert (sin-math 0) 0.0)
!(assert (asin-math 0) 0.0)
!(assert (cos-math 0) 1.0)
!(assert (acos-math 1) 0.0)
!(assert (tan-math 0) 0.0)
!(assert (atan-math 0) 0.0)
!(assert (isnan-math 0.0) False)
!(assert (isinf-math 0.0) False)
!(assert (min-atom (2 6 7 4 9 3)) 2)
!(assert (max-atom (2 6 7 4 9 3)) 9)
;;;;;;;NEXT EXAMPLE:
!(import! &self ../lib/lib_he)

(= (div $x $y $accum)
   (chain (eval (- $x $y)) $r1
     (chain (eval (< $r1 0)) $r2
       (chain (unify $r2 True
         $accum
         (chain (eval (+ 1 $accum)) $inc
           (chain (eval (div $r1 $y $inc)) $r4 $r4)
         )) $r3 $r3
       )
     )
   )
)

!(assert (chain (eval (div 350000 5 0)) $rr $rr) 70000)
;;;;;;;NEXT EXAMPLE:
!(import! &self ../lib/lib_he)

!(assert (quote (+ 1 2)) (quote (+ 1 2)))

!(assert (eval (+ 1 2)) 3)

!(assert (unquote (quote (+ 1 2))) 3)

!(assert (noreduce-eq (+ 1 2) (+ 1 2)) True)

!(assert (noreduce-eq (+ 1 2) 3) False)
;;;;;;;NEXT EXAMPLE:
!(import! &self ../lib/lib_he)

!(assert (is-function (-> Atom Atom)) True)
!(assert (is-function Atom) False)
;TODO:
;(: type1 Type)
;!(type-cast A type1 &self)
;!(type-cast 1 type1 &self)
!(assert (first-from-pair (A B)) A)
!(assert (second-from-pair (A B)) B)
!(assert (match-type-or True Number Bool) True)
;;;;;;;NEXT EXAMPLE:
(= (mymap $f ()) ())
(= (mymap $f (cons $x $xs)) (cons ($f $x) (mymap $f $xs)))

(= (eq $a $b) (== $a $b))

!(assert (mymap (== 1) (1 2 3)) (mymap (eq 1) (1 2 3)))
;;;;;;;NEXT EXAMPLE:
(= (f1a)
   (foldl-atom (1 2 3 4) 0 $acc $x (+ $acc $x)))
(= (f2a)
   (map-atom (1 2 3) $x (+ $x 1)))
(= (f3a)
   (filter-atom (1 2 3 4 5) $x (> $x 3)))

(= (foldfun $a $b) (+ $a $b))
(= (mapfun $a) (+ $a 1))
(= (filterfun $x) (> $x 3))

(= (f1b)
   (foldl-atom (1 2 3 4) 0 foldfun))
(= (f2b)
   (map-atom (1 2 3) mapfun))
(= (f3b)
   (filter-atom (1 2 3 4 5) filterfun))

!(assert (f1a) 10)
!(assert (f2a) (2 3 4))
!(assert (f3a) (4 5))

!(assert (f1b) 10)
!(assert (f2b) (2 3 4))
!(assert (f3b) (4 5))


(= (foldfun2 $a $b) (append $a $b))
!(foldl-atom ((1 2) (3 4) (5 6)) () $acc $x (append $acc $x))
;;;;;;;NEXT EXAMPLE:
(= (find-divisor $n $test-divisor)
   (if (> (* $test-divisor $test-divisor) $n)
       $n
       (if (== 0 (% $n $test-divisor)) 
           $test-divisor
           (find-divisor $n (+ $test-divisor 1)))))

(= (prime? $n)
   (== $n (find-divisor $n 2)))

;multi-threaded concurrency running each option till the bitter end:
!(assert (collapse (hyperpose ((prime? 5353725700019)    ;cheap
                             (prime? 5378181100003)    ;cheap
                             (prime? 5421844300001)    ;cheap
                             (prime? 5473443100001)))) ;cheap => cheap overall
       (True True True True))

;multi-threaded concurrency running only until the first one succeeds:
!(assert (once (hyperpose ((prime? 535372570000000063)    ;expensive
                         (prime? 537818110000000001)    ;expensive
                         (prime? 5421844300001)         ;cheap
                         (prime? 547344310000000013)))) ;expensive => cheap overall
       True)
;;;;;;;NEXT EXAMPLE:
(= (f $x) (* $x $x))

!(assert (f 1) 1)
;;;;;;;NEXT EXAMPLE:
!(assert (if (is-var a) (() (+ 1 1)) (+ 2 2)) 4)
;;;;;;;NEXT EXAMPLE:
!(assert (if (is-var $A) 
           (if True 42 lol) 
           (+ 2 2)) 42)
;;;;;;;NEXT EXAMPLE:
!(assert (if (if (== 42 42) True False)
           (if True 42 lol) 
           (+ 2 2)) 42)
;;;;;;;NEXT EXAMPLE:
(= (if-nondet $y)
  (if (superpose $y) a b))
  
(= (case-nondet $y)
   (case (superpose $y)
         ((True a)
          (False b))))

!(assert (collapse (if-nondet (True False True))) (a b a))

!(assert (collapse (case-nondet (True False True))) (a b a))
;;;;;;;NEXT EXAMPLE:
!(assert (if (> 1 2) (3 4) (5 6))
       (5 6))
;;;;;;;NEXT EXAMPLE:
!(assert (if True 42) 42)
;;;;;;;NEXT EXAMPLE:
(= (f $X $Y)
   (append ($X) $Y))

(= (g $X $Y $Z)
   (append ((#+ $X $Z)) $Y))

;List destructuring:
!(assert (let (cons $Head $Tail) (1 2 3 4 5 6) ($Head $Tail))
            (1 (2 3 4 5 6)))

;But instead it works for any relational functions:
!(assert (let (f $Head $Tail) (1 2 3 4 5 6) ($Head $Tail))
            (1 (2 3 4 5 6)))

;More complex case:
!(assert (let (g $X $Y 35) (42 2 3)
            ($X $Y 40))
       (7 (2 3) 40))
;;;;;;;NEXT EXAMPLE:
; iterator state is just a number
(= (make-nat-iter) 0)

(= (iter-next $N)
   (let* (($X $N)
          ($Next (+ $N 1)))
         ($X $Next)))

!(assert (let* (($it (make-nat-iter))
              (($x1 $it1) (iter-next $it))
              (($x2 $it2) (iter-next $it1))
              (($x3 $it3) (iter-next $it2)))
             ($x1 $x2 $x3))
       (0 1 2))
;;;;;;;NEXT EXAMPLE:
!(assert (let ($x (42 (if (== $x 2) 43 44))) (3 (42 $z)) (+ $x $z)) 47)
;;;;;;;NEXT EXAMPLE:
(= (f)
   (let* ((($f1 $c1 3) (1 2 $d1)))
         ($f1 $c1 $d1)))

!(assert (f)
       (1 2 3))
;;;;;;;NEXT EXAMPLE:
!(assert (let* (($x 1) ($y 2)) (+ $x $y)) 3)
;;;;;;;NEXT EXAMPLE:
(= (f $x) 42)

(= (progme) 
   (let $y (superpose (2 3 4 5))
                  (if (> $y 2)
                      (case (1 $y) (((1 3) (f 0))
                                    ((1 4) (42 42))
                                    ($else (42 42 42))))
                      answertoeverything)))

!(assert (collapse (progme))
       (answertoeverything 42 (42 42) (42 42 42)))
;;;;;;;NEXT EXAMPLE:
!(import! &self (library lib_roman))

!(assert (map-flat (+ 1) (1 2 3)) (2 3 4))
;;;;;;;NEXT EXAMPLE:
;First check out constanthead.metta for the simpler case:
(= (len ()) 0)
(= (len (cons $Head $Tail))
   (let $N0 (len $Tail)
        (+ $N0 1)))

!(assert (let (cons $Head $Tail) (1 2 3 4 5 6) ($Head $Tail))
            (1 (2 3 4 5 6)))
!(assert (len (1 2 3)) 3)
!(assert (cons 42 ()) (42))
;Now please out functionhead.metta for a generalization of the idea!
;;;;;;;NEXT EXAMPLE:
(= (successor b a) True)
(= (successor c b) True)
(= (successor d c) True)
(= (successor e d) True)
(= (successor f e) True)
(= (successor g f) True)

(= (later-in-alphabet $X $Y)
   (successor $X $Y))

(= (later-in-alphabet $X $Y)
   (and (successor $X $Z) (later-in-alphabet $Z $Y)))

;Alternative formulation of the previous function (still only with PeTTa though)
;(= (later-in-alphabet $X $Y)
;   (let $temp (successor $X $Z)
;        (later-in-alphabet $Z $Y)))

!(assert (collapse ((later-in-alphabet d $1) $1))
       ((True c) (True b) (True a)))
;;;;;;;NEXT EXAMPLE:
(= (myf $M)
   (and (and (member a $M)
             (member b $M))
        (== (size-atom $M) 3)))

!(assert (let $constraint (once (myf $M)) $M)
       (a b))
;;;;;;;NEXT EXAMPLE:
(= (hide $1) (empty))

!(hide ((add-atom &self (friend tim tom))
        (add-atom &self (friend tom tam))
        (add-atom &self (friend sim som))
        (add-atom &self (friend som sam))))

!(hide (match &self (, (friend $1 $2) (friend $2 $3))
                    ((add-atom &self (transitive $1 $2 $3))
                     (remove-atom &self (friend $1 $2))
                     (remove-atom &self (friend $2 $3)))))

!(assert (msort (collapse (match &self (transitive $1 $2 $3) (transitive $1 $2 $3))))
       ((transitive sim som sam) (transitive tim tom tam)))
       
;;;;;;;NEXT EXAMPLE:
(= (hide $1) (empty))

!(hide ((add-atom &self (friend tim tom))
        (add-atom &self (friend tom tam))
        (add-atom &self (friend sim som))
        (add-atom &self (friend som sam))))

!(hide (match &self (friend $1 $2)
              (match &self (friend $2 $3) 
                     ((add-atom &self (transitive $1 $2 $3))
                      (remove-atom &self (friend $1 $2))
                      (remove-atom &self (friend $2 $3))))))

!(assert (msort (collapse (match &self (transitive $1 $2 $3) (transitive $1 $2 $3))))
       ((transitive sim som sam) (transitive tim tom tam)))
       
;;;;;;;NEXT EXAMPLE:
(a b)
(a c)

(= (match-single-via-cut $space $pattern $outPattern)
   (let* (($x (match $space $pattern $outPattern))
          ($temp (cut)))
         $x))

(= (match-single-via-once $space $pattern $outPattern)
   (once (match $space $pattern $outPattern)))

!(assert (collapse (match-single-via-cut &self (a $x) (a $x))) ((a b)))
!(assert (collapse (match-single-via-once &self (a $x) (a $x))) ((a b)))
;;;;;;;NEXT EXAMPLE:
(= (match-types $A $B $Then $Else) (if (== $A $B) $Then $Else))

(= (match-type-or $value $type1 $type2) (match-types $type1 $type2 True $value))

!(assert (match-type-or True Number Number) True)
!(assert (match-type-or False Number Number) True)
!(assert (match-type-or True Number Bool) True)
!(assert (match-type-or False Number Bool) False)
;;;;;;;NEXT EXAMPLE:
(= (rewriteK $t $n)
   (if (== $n 0)
       done
       (let* (($_1 (add-atom &self (num (M $t))))
              ($_2 (add-atom &self (num (W $t))))
              ($_3 (add-atom &self (num (C $t)))))
             ((rewriteK (M $t) (- $n 1))
              (rewriteK (W $t) (- $n 1))))))

;Apply the rewrites K times, then match:
(= (mate-space-demo $K)
   (let* (($s (add-atom &self (num Z)))
          ($g (rewriteK Z $K)))
          (match &self (num $1) (num $1))))

!(assert (length (collapse (mate-space-demo 19))) 1572862)
;;;;;;;NEXT EXAMPLE:
!(assert (pow-math 2 3) 8)
!(assert (sqrt-math 9) 3.0)
!(assert (abs-math -5) 5)
!(assert (log-math 10 100) 2.0)
!(assert (trunc-math 5.6) 5)
!(assert (ceil-math 5.2) 6)
!(assert (floor-math 5.8) 5)
!(assert (round-math 5.4) 5)
!(assert (round-math 5.6) 6)
!(assert (sin-math 0) 0.0)
!(assert (asin-math 0) 0.0)
!(assert (cos-math 0) 1.0)
!(assert (acos-math 1) 0.0)
!(assert (tan-math 0) 0.0)
!(assert (atan-math 0) 0.0)
!(assert (isnan-math 0.0) False)
!(assert (isinf-math 0.0) False)
!(assert (min-atom (2 6 7 4 9 3)) 2)
!(assert (max-atom (2 6 7 4 9 3)) 9)
;;;;;;;NEXT EXAMPLE:
!(assert (get-metatype (foo 1 2)) Expression)
!(assert (get-metatype (a b)) Expression)
!(assert (get-metatype 1) Grounded)
!(assert (get-metatype +) Grounded)
!(assert (get-metatype $x) Variable)
!(assert (get-metatype a) Symbol)
;;;;;;;NEXT EXAMPLE:
!(assert (progn (add-atom &self (friend sam tom))
              (remove-atom &self (friend sam tom))
              (add-atom &self (friend sam tim))
              (match &self (friend sam $1) $1))
       tim)

!(assert (prog1 1 2 3) 1)
!(assert (progn 1 2 3) 3)
;;;;;;;NEXT EXAMPLE:
;nondeterministically returning integers withing range:
(= (range $K $N)
   (if (< $K $N)
       (superpose ($K (range (+ $K 1) $N)))
       (empty)))

!(forall (range 1 5)
         (|-> ($x)
              (add-atom &s1 (num $x)))) ;shortcuts when one returns false

;Add only one commited option: (select)
!(let $x (once (range 1 5))
         (add-atom &s2 (num $x)))

!(assert (collapse (get-atoms &s1))
       ((num 1) (num 2) (num 3) (num 4)))

!(assert (collapse (get-atoms &s2))
       ((num 1)))

(= (gen) 1)
(= (gen) 2)
(= (gen) 3)

!(assert (foldall (|-> ($x $y) (+ $x $y)) (gen) 0) 6)

;;;;;;;NEXT EXAMPLE:
!(let $x (cons set (superpose ((1 (superpose (a b c)))
                               (2 (superpose (d e f)))
                               (3 (superpose (a b))))))
      (add-atom &self $x))

!(assert (collapse (match &self (set $x $y) (set $x $y)))
       ((set 1 a) (set 1 b) (set 1 c) (set 2 d) (set 2 e) (set 2 f) (set 3 a) (set 3 b)))
;;;;;;;NEXT EXAMPLE:
(= (mycalc $x $y)
   (+ $x $y))

(= (mycalc $x $y)
   (- $x $y))

!(assert (collapse (mycalc 1 2))
       (3 -1))
;;;;;;;NEXT EXAMPLE:
!(assert (unique-atom (a b c d d)) (a b c d))
!(assert (union-atom (a b b c) (b c c d)) (a b b c b c c d))
!(assert (intersection-atom (a b c c) (b c c c d)) (b c c))
!(assert (subtraction-atom (a b b c) (b c c d)) (a b))
;;;;;;;NEXT EXAMPLE:
(: myinterpreter (-> Expression %Undefined%))
(= (myinterpreter $code)
   (let $temp (println! (Runtime-interpreting-code $code))
        (eval $code)))

(= (w) 42)
(= (v) 43)

!(assert (myinterpreter (if (== 1 1) (w) (v))) 42)
!(assert (myinterpreter (if (== 1 2) (w) (v))) 43)
;;;;;;;NEXT EXAMPLE:
(foo 1)
(foo 2)

(= (match-single $space $pat $ret)
   (once (match $space $pat $ret)))

!(let $x (match-single &self (foo $1) $1) (add-atom &self (bar $x)))

!(assert (collapse (match &self (bar $1) (bar $1)))
       ((bar 1)))
;;;;;;;NEXT EXAMPLE:
(: apply (-> (-> $tx $ty) $tx $ty))
(= (apply $f $x) ($f $x))
!(apply not False) ; True
!(get-type (apply not False))
!(assert (let (get-type apply) (-> (-> Bool Bool) Bool $result) $result)
       Bool)
;;;;;;;NEXT EXAMPLE:
(= (mp) (+))

!(assert (mp 1 1) 2)

(= (.. $f1 $f2 $arg) ($f1 ($f2 $arg)))

(= (plus1times2) (.. (* 2) (+ 1)))

!(assert (plus1times2 1) 4)
;;;;;;;NEXT EXAMPLE:
!(import! &self (library lib_patrick))

(= (fib-step $i ($a $b))
   ($b (+ $a $b)))

(= (fib $n)
   (first (iterate 0 $n (0 1) fib-step)))

!(assert (fib 100) 354224848179261915075)
;;;;;;;NEXT EXAMPLE:
!(import! &self (library lib_patrick))

(= (quad-step $dummy ($t $i $sum))
   (if (== $i $t)
       ( (+ $t 1) 1 (+ $sum (* $t $i)) )
       ( $t (+ $i 1) (+ $sum (* $t $i)) )))

(= (quad-sum $n)
   (last (iterate 0 (/ (* $n (+ $n 1)) 2) (1 1 0) quad-step)))

!(assert (quad-sum 1000) 125417041750)
;;;;;;;NEXT EXAMPLE:
!(import! &self (library lib_patrick))

(= (mirror (@ $L (cons $head $tail)))
   (append (reverse $L) $tail))

!(assert (mirror (h a n n e s)) (s e n n a h a n n e s))

!(assert (collapse (for $x (1 2 3 4 5 6)
                      (if (> $x 3) $x)))
       (4 5 6))
      
!(assert (iterate 0 10
                1 (|-> ($i $x)
                       (+ $x $i)))
       46)
;;;;;;;NEXT EXAMPLE:
;Peano builders:
(= (expandK $expression $n)
   (if (== $n 0)
       done
       (let $temp1 (add-atom &self (num $expression))
            (expandK (S $expression) (- $n 1)))))

;Peano demo:
(= (demo-peano $K)
   (expandK Z $K))

!(demo-peano 2500)
!(assert (length (collapse (match &self (num $1) $1))) 2500)
;;;;;;;NEXT EXAMPLE:
(= (add-atom-no-duplicate $Space $Atom)
   (if (== () (collapse (once (match $Space $Atom $Atom))))
       (add-atom $Space $Atom)
       (empty)))

;For every existing num($t), add num(S $t):
(= (expand-once)
   (case (match &self (num $t) $t) 
         (($x (add-atom-no-duplicate &self (num (S $x)))))))

;Peano builders:
(= (expandK $n)
   (if (== $n 0)
       done
       (let $temp1 (expand-once)
            (expandK (- $n 1)))))

;Peano demo:
(= (demo-peano $K)
   (let* (($s (add-atom &self (num Z)))
          ($g (expandK $K)))
         (match &self (num $1) $1)))

!(assert (length (collapse (demo-peano 300))) 301)
;;;;;;;NEXT EXAMPLE:
(1 != 2) (1 != 3) (1 != 4) (1 != 5) (1 != 6) (1 != 7) (1 != 8) (2 != 1) (2 != 3) (2 != 4) (2 != 5) (2 != 6) (2 != 7) (2 != 8)
(3 != 1) (3 != 2) (3 != 4) (3 != 5) (3 != 6) (3 != 7) (3 != 8) (4 != 1) (4 != 2) (4 != 3) (4 != 5) (4 != 6) (4 != 7) (4 != 8)
(5 != 1) (5 != 2) (5 != 3) (5 != 4) (5 != 6) (5 != 7) (5 != 8) (6 != 1) (6 != 2) (6 != 3) (6 != 4) (6 != 5) (6 != 7) (6 != 8)
(7 != 1) (7 != 2) (7 != 3) (7 != 4) (7 != 5) (7 != 6) (7 != 8) (8 != 1) (8 != 2) (8 != 3) (8 != 4) (8 != 5) (8 != 6) (8 != 7)
(E $_1 $_2 $_3 $_4 $_5 $_6 $_7 $_8 1 (___ $_1 $_2 $_3 $_4 $_5 $_6 $_7 $_8) )
(E $_1 $_2 $_3 $_4 $_5 $_6 $_7 $_8 2 ($_1 ___ $_2 $_3 $_4 $_5 $_6 $_7 $_8) )
(E $_1 $_2 $_3 $_4 $_5 $_6 $_7 $_8 3 ($_1 $_2 ___ $_3 $_4 $_5 $_6 $_7 $_8) )
(E $_1 $_2 $_3 $_4 $_5 $_6 $_7 $_8 4 ($_1 $_2 $_3 ___ $_4 $_5 $_6 $_7 $_8) )
(E $_1 $_2 $_3 $_4 $_5 $_6 $_7 $_8 5 ($_1 $_2 $_3 $_4 ___ $_5 $_6 $_7 $_8) )
(E $_1 $_2 $_3 $_4 $_5 $_6 $_7 $_8 6 ($_1 $_2 $_3 $_4 $_5 ___ $_6 $_7 $_8) )
(E $_1 $_2 $_3 $_4 $_5 $_6 $_7 $_8 7 ($_1 $_2 $_3 $_4 $_5 $_6 ___ $_7 $_8) )
(E $_1 $_2 $_3 $_4 $_5 $_6 $_7 $_8 8 ($_1 $_2 $_3 $_4 $_5 $_6 $_7 ___ $_8) )
(E $_1 $_2 $_3 $_4 $_5 $_6 $_7 $_8 9 ($_1 $_2 $_3 $_4 $_5 $_6 $_7 $_8 ___) )
!(assert (length (collapse (match &self
                                (, ($_1 != $_2)
                                   ($_2 != $_3) ($_3 != $_1)
                                   ($_3 != $_4) ($_4 != $_2) ($_4 != $_1)
                                   ($_4 != $_5) ($_5 != $_3) ($_5 != $_2) ($_5 != $_1)
                                   ($_5 != $_6) ($_6 != $_4) ($_6 != $_3) ($_6 != $_2) ($_6 != $_1)
                                   ($_6 != $_7) ($_7 != $_5) ($_7 != $_4) ($_7 != $_3) ($_7 != $_2) ($_7 != $_1)
                                   ($_7 != $_8) ($_8 != $_6) ($_8 != $_5) ($_8 != $_4) ($_8 != $_3) ($_8 != $_2) ($_8 != $_1)
                                   (E $_1 $_2 $_3 $_4 $_5 $_6 $_7 $_8 $x $state))
                                (state1 $state))))
       362880)
;;;;;;;NEXT EXAMPLE:
!(import! &self ../lib/lib_pln)

(= (STV A) (stv 0.5 0.9))
(= (STV B) (stv 0.25 0.9))
(= (STV C) (stv 0.25 0.9))
(= (STV D) (stv 0.5 0.9))

(= (kb)
   ((Sentence ((Inheritance A B) (stv 0.25 0.9)) (1))
    (Sentence ((Inheritance A C) (stv 0.25 0.9)) (2))
    (Sentence ((Inheritance B D) (stv 0.5 0.9)) (3))
    (Sentence ((Inheritance C D) (stv 0.5 0.9)) (4))
   ))

!(assert (PLN.Query (kb) (Inheritance A D))
       ((stv 0.5 0.9473684210526316) (1 2 3 4)))
;;;;;;;NEXT EXAMPLE:
;Clean separation from Python calls
(= (make-object) (py-call (types.SimpleNamespace)))
(= (get-attribute $obj $name) (py-call (getattr $obj $name)))
(= (set-attribute $obj $name $value) (py-call (setattr $obj $name $value)))
(= (import $name) (py-call (importlib.import_module $name)))
(= (math.pi) (get-attribute (import math) pi))

;Clean program using objects and pi: 
!(assert (let* (($obj (make-object))
              ($temp (set-attribute $obj foo (math.pi))))
             (get-attribute $obj foo))
       3.141592653589793)
;;;;;;;NEXT EXAMPLE:
(: Z Nat)
(: S (-> Nat Nat))
(: Greater (-> Nat Nat Bool))
(= (Greater (S $x) Z)
   True)
(= (Greater Z $x)
   False)
(= (Greater (S $x) (S $y))
   (Greater $x $y))

!(assert (Greater (S Z) (S Z)) false)    ; False
!(assert (Greater (S (S Z)) (S Z)) true) ; True
;;;;;;;NEXT EXAMPLE:
(: blacksmith (-> Metal Sword))
(: blacksmith (-> Metal Paperclip))
(: iron Metal)
(: gold Metal)

!(assert (get-type iron) Metal)
!(assert (collapse (get-type blacksmith)) ((-> Metal Sword) (-> Metal Paperclip)))
!(assert (collapse (get-type (blacksmith iron))) (Sword Paperclip))
!(assert (collapse (get-type (iron blacksmith))) ((Metal (-> Metal Sword)) (Metal (-> Metal Paperclip))))
;;;;;;;NEXT EXAMPLE:
(= (range $K $N)
   (if (< $K $N)
       (superpose ($K (range (+ $K 1) $N)))
       (empty)))

!(let* (($k (range 0 inf))
        ($inp (readln!))
        ($quotedfunc (quote (= $X $Y)))
        ($output (if (= $inp $quotedfunc)
                        (add-atom &self $inp)
                        (eval $inp)))
        ($printed (println! $output)))
       (empty))
;;;;;;;NEXT EXAMPLE:
(= (f $x)
   (* $x 2))

(= (g $f $x)
   (justdata $f $x))

(= (h $f $x)
   ($f $x))

(= (notjustdata $x)
   f)

(= (datawithnondatacomponent)
   ((lol (f 42))))

!(assert ((f 21) (g f 2) (h f 2) ((notjustdata 42) 21) (datawithnondatacomponent))
       (42 (justdata f 2) 4 42 ((lol 84))))
;;;;;;;NEXT EXAMPLE:
!(add-atom &self (= (f $x $y) (+ $x $y)))
!(add-atom &self (= (g $x $y) (+ $x $y)))
!(remove-atom &self (= (f $x $y) (+ $x $y)))
!(assert (f 3 4) (f 3 4))
!(assert (g 3 4) 7)

!(add-atom &self (my test))
!(remove-atom &self (my test))
!(assert (collapse (match &self (my test) (my test))) ())
;;;;;;;NEXT EXAMPLE:
(foo 1)
(foo 2)
(foo 42 42)
(foo (42 42))

!(bar 42)
!(bar 43)

(= (answer) 42)

!(assert (space (msort (collapse (superpose ((match &self (foo $1) (foo $1))
                                           (match &self (foo $1 $2) (foo $1 $2))
                                           (match &self (bar $1) (bar $1)))))) (answer))
       (space ((foo 1) (foo 2) (foo 42 42) (foo (42 42))) 42))
;;;;;;;NEXT EXAMPLE:
!(add-atom &wuspace (wu))
!(add-atom &wuspace (wu 42))

!(assert (collapse (match &wuspace ($1) ($1))) ((wu)))
!(assert (collapse (match &wuspace ($1) (hu $1))) ((hu wu)))
!(assert (collapse (match &wuspace ($1) $1)) (wu))
!(assert (msort (collapse (match &wuspace $1 $1))) (msort (collapse (get-atoms &wuspace))))
!(assert (msort (collapse (match &wuspace $1 (wu $1)))) ((wu (wu)) (wu (wu 42))))
;;;;;;;NEXT EXAMPLE:
!(import! &self ../lib/lib_spaces)

(friend a b)
(friend b c)

!(assert (collapse (if (find &self (friend $a $b))
                     (if (find &self (friend $b $c))
                         (FoundChain $a $b $c)
                         (MissedSecondPiece))
                     (MissedAllPieces)))
       ((FoundChain a b c) (MissedSecondPiece)))
;;;;;;;NEXT EXAMPLE:
(= (matchtrickery)
   (let* (($t1 (add-atom &self (foo a)))
          ($t2 (add-atom &self (foo b))))
         (match &self (foo $1) (bar $1))))

!(assert (collapse (matchtrickery))
       ((bar a) (bar b)))
;;;;;;;NEXT EXAMPLE:
!(import! &self (library lib_spaces))

(friend tim tom)

(= (f $x) 42)

!(remove-all-atoms &self)

!(assert (collapse (get-atoms &self))
       ())
;;;;;;;NEXT EXAMPLE:
!(import! &self (library lib_spaces))

;fail test:
!(assert (succeedsPredicate (&self friend tim tom))
       False)

;metta s-expr:
(friend a b)
!(assert (if (succeedsPredicate (&self friend $a $b))
           ($a $b)
           NotFound)
       (a b))
;;;;;;;NEXT EXAMPLE:
(= (f1 $f $a) (if (< $a 0)
                  ($f nevercalled 42)
                  (if (== $a 0) 
                      (f2 $f (- $a 1))
                      finish)))
(= (f2 $f $a) (if (< $a 0)
                  ($f nevercalled 42)
                  (f1 $f $a)))

!(assert (f1 + 2) finish)

(= (f3 $f $n) (if (== $n 0) finish (f4 $f $n)))
(= (f4 $f $n) (f3 $f (- $n 1)))

!(assert (f3 + 1) finish)
;;;;;;;NEXT EXAMPLE:
(= (g $x) $x)

(: f (-> Atom Number Atom))
(: f (-> Atom String Atom))
(= (f $g $x)
   (repra ($g $x)))

!(f g 42)

!(assert (match &self (: f_Spec_[g] (-> Atom Number Atom)) ok) ok)
!(assert (match &self (: f_Spec_[g] (-> Atom String Atom)) ok) ok)
;;;;;;;NEXT EXAMPLE:
!(bind! state (new-state rest))
!(assert (get-state state) rest)
!(change-state! state active)
!(assert (get-state state) active)
;;;;;;;NEXT EXAMPLE:
!(assert (collapse (unique (superpose (a b c d d)))) (a b c d))

!(assert (collapse (union (superpose (a b b c)) (superpose (b c c d)))) (a b b c b c c d))

!(assert (collapse (intersection (superpose (a b c c)) (superpose (b c c c d)))) (b c c))

!(assert (collapse (subtraction (superpose (a b b c)) (superpose (b c c d)))) (a b))
;;;;;;;NEXT EXAMPLE:
(= (TupleConcat $Ev1 $Ev2) (collapse (superpose ((superpose $Ev1) (superpose $Ev2)))))

(= (range $K $N)
   (if (< $K $N)
       (TupleConcat ($K) (range (+ $K 1) $N))
       ()))

!(assert (range 1 10)
       (1 2 3 4 5 6 7 8 9))
;;;;;;;NEXT EXAMPLE:
(= (progme)
   ((collapse (superpose ((superpose (a b c)) (superpose (x y z)))))
    (collapse (superpose (a b c)))
    (collapse (superpose ((superpose (a b c)))))
    (collapse (superpose ((superpose (a b c)) x y z )))))

!(assert (progme)
       ((a b c x y z) (a b c) (a b c) (a b c x y z)))
;;;;;;;NEXT EXAMPLE:
;test deactivated with file name extension as it is computationally expensive, only feasible with the compiler
(= (find-divisor $n $test-divisor)
   (if (> (* $test-divisor $test-divisor) $n)
       $n
       (if (== 0 (% $n $test-divisor)) 
           $test-divisor
           (find-divisor $n (+ $test-divisor 1)))))

(= (prime? $n)
   (== $n (find-divisor $n 2)))

!(assert ((prime? 53537257)
        (prime? 53781811)
        (prime? 54218443)
        (prime? 54734431))
       (True True True True))
;;;;;;;NEXT EXAMPLE:
(= (program1 $Y) (let $X $Y (collapse (superpose (12 (+ $X 4))))))

(= (program2 $Y) (let $list (let $L (1 2 3) (collapse (superpose $L))) (superpose $list)))

(= (program3 $x) (if (== $x 2) (let $z (superpose ((if (< $x 10) (superpose ((42 43))) 43))) $z) (let $z 4 $z)))

(= (program4) (collapse ((program1 42) (program2 42) (program3 2))))

!(assert (program4)
       (((12 46) 1 (42 43)) ((12 46) 2 (42 43)) ((12 46) 3 (42 43))))
;;;;;;;NEXT EXAMPLE:
;Clean separation from Python calls
(= (tensor $x) (py-call (torch.tensor $x)))
(= (mul $A $B) (py-call (torch.matmul $A $B)))
(= (tensor2list $x) (py-call (.tolist $x)))
(= (size2list $x) (py-call (list $x)))
(= (shape $x) (size2list (py-call (getattr $x shape))))

;Clean program using Tensors:
(= (myprog)
   (let* (($A (tensor ((1 2 3)
                       (4 5 6))))
          ($B (tensor (( 7  8  9 10)
                       (11 12 13 14)
                       (15 16 17 18))))
          ($C (mul $A $B))
          ($S (shape $C))
          ($L (tensor2list $C)))
         ($L $S)))

!(assert (myprog)
       (((74 80 86 92) (173 188 203 218)) (2 4)))
;;;;;;;NEXT EXAMPLE:
!(assert (progn (translatePredicate (is $x 2))
              (translatePredicate (+ $x 40 $z)) $z)
       42)
;;;;;;;NEXT EXAMPLE:
(= (fib-tr $n $a $b)
   (if (== $n 0)
       $a
       (fib-tr (- $n 1) $b (+ $a $b))))

(= (fib $n)
   (fib-tr $n 0 1))
   

(= (compilefib $n)
   (fib $n))

;can be commented out but then the following will be slower:
!(add-translator-rule! compilefib)

(= (smartfun $b)
   (* (compilefib 10) $b))

!(assert (smartfun 42) 2310)
;;;;;;;NEXT EXAMPLE:
(: for (-> Expression Expression Expression Expression))
(= (for $var $collection $body)
   (quote (let $var (superpose $collection)
                    $body)))

!(add-translator-rule! for)

(= (myfun $L)
   (for $x $L
        (if (== (% $x 2) 0)
            (even $x)
            (odd $x))))

!(assert (collapse (myfun (3 4)))
       ((odd 3) (even 4)))
;;;;;;;NEXT EXAMPLE:
(= (runtime42 $arg)
   (cons 42 $arg))

(= (compileeval42 $arg)
   (cons 42 $arg))

(= (compile42 $arg)
   (quote (cons 42 $arg)))

!(add-translator-rule! compileeval42)
!(add-translator-rule! compile42)

!(assert (runtime42 (43)) (42 43))
!(assert (compileeval42 (43)) (42 43))
!(assert (compile42 (43)) (42 43))
;;;;;;;NEXT EXAMPLE:
(= (f) (g))

(= (g) 42)

(= (h) (g))

!(assert (f) 42)

!(assert (h) 42)
;;;;;;;NEXT EXAMPLE:
;get-type extension for numbers:
(= (get-type $x)
   (catch (if (== (% $x 2) 0)
              EvenNumber)))

;try it:
(: f (-> EvenNumber EvenNumber EvenNumber))
(= (f $x $y)
   (+ $x $y))

!(assert (f 2 4) 6)

;get-type extension for list of even numbers:
(= (get-type (cons $head $tail))
   (if (== (get-type $head) EvenNumber)
       (if (== $tail ())
           EvenNumberList
           (get-type $tail))))

;try it:
(: g (-> EvenNumberList Bool))
(= (g $L)
   True)

!(assert (g (2 4 6)) True)
;;;;;;;NEXT EXAMPLE:
(: f (-> Type1 Type1))
(: f (-> Type2 Type2))
(= (f $a)
   (if (== $a T1in)
       T1out
       (if (== $a T2in)
           T2out
           Tdefault)))

(: T1in Type1)
(: T1out Type1)
(: T2in Type2)
(: T2out Type2)

(: T3in Type1)
(: Tdefault Type2)

!(assert (f T1in) T1out)
!(assert (f T2in) T2out)
!(assert (f T3in) ()) ;Type1 of T3in does not go along with Type2 output
(: T3in Type2)      ;But if we make T3in also of Type2 then it is fine if output is Type2:
!(assert (f T3in) Tdefault)
;;;;;;;NEXT EXAMPLE:
(= (check_xor $source $destination)
   (if (xor (== $source $destination)
            (> $source $destination))
            42
            0))

!(assert (check_xor 2 2) 42)
!(assert (check_xor 4 2) 42)